# -*- coding:utf-8 -*-
# 导入 BGE-M3 嵌入函数，用于生成文档和查询的向量表示
import torch.cuda
from milvus_model.hybrid import BGEM3EmbeddingFunction
# 导入 Milvus 相关类，用于操作向量数据库
from pymilvus import MilvusClient, DataType, AnnSearchRequest, WeightedRanker
# 导入 Document 类，用于创建文档对象
from langchain.docstore.document import Document
# 导入 CrossEncoder，用于重排序和 NLI 判断
from sentence_transformers import CrossEncoder
# 导入 hashlib 模块，用于生成唯一 ID 的哈希值
import hashlib
import sys, os
import requests
# 路径设置：先把 core、rag_qa 和项目根目录加入 sys.path，再导入项目内模块。
# 否则从其他目录启动时 `from document_processor import *` 和 `from base import logger` 会 ImportError。
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/
sys.path.insert(0, current_dir)
sys.path.insert(0, rag_qa_path)
sys.path.insert(0, project_root)
from document_processor import *
from base import logger, Config


conf = Config()


class RemoteEmbeddings:
    """远程 OpenAI 兼容 /embeddings 嵌入（SiliconFlow 等，如 BAAI/bge-m3）。

    与本地 BGEM3 保持同一调用面：可调用，返回 {"dense": ..., "sparse": ...}。
    远程接口只出稠密向量，sparse 恒为 None（下游据此降级稀疏检索）。
    """

    def __init__(self, url, api_key, model, dim):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=url)
        self.model = model
        self.dim = dim

    def __call__(self, texts):
        import numpy as np
        resp = self.client.embeddings.create(model=self.model, input=texts)
        # 按输入顺序排好（OpenAI 返回 data 顺序稳定，仍按 index 排序更稳妥）
        ordered = sorted(resp.data, key=lambda x: x.index)
        dense = np.array([d.embedding for d in ordered], dtype=np.float32)
        return {"dense": dense, "sparse": None}


class RemoteReranker:
    """远程 /rerank 重排序（Cohere 兼容返回：results[].relevance_score）。

    与本地 CrossEncoder.predict(pairs) 同签名：predict([(q, doc), ...]) → [score, ...]。
    """

    def __init__(self, url, api_key, model):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def predict(self, pairs):
        if not pairs:
            return []
        query = pairs[0][0]
        documents = [doc for _, doc in pairs]
        resp = requests.post(
            f"{self.url}/rerank",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "query": query,
                  "documents": documents, "top_k": len(documents)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        scores = [0.0] * len(documents)
        for r in data.get("results", []):
            scores[r["index"]] = r.get("relevance_score", 0.0)
        return scores


# core/vector_store.py
# 定义 VectorStore 类，封装向量存储和检索功能
class VectorStore:
    # 初始化方法，设置向量存储的基本参数
    def __init__(self,
                 collection_name=conf.MILVUS_COLLECTION_NAME,
                 host=conf.MILVUS_HOST,
                 port=conf.MILVUS_PORT,
                 database=conf.MILVUS_DATABASE_NAME):
        # 设置 Milvus 集合名称
        self.collection_name = collection_name
        # 设置 Milvus 主机地址
        self.host = host
        # 设置 Milvus 端口号
        self.port = port
        # 设置 Milvus 数据库名称
        self.database = database
        # 设置日志记录器
        self.logger = logger
        # 检查CUDA是否可用
        self.device ='cuda' if torch.cuda.is_available() else 'cpu'
        # 日志提醒使用的是什么设备
        self.logger.info(f"使用设置：{self.device}")

        # ---- 嵌入模型：配了远程 url 走 API，否则用本地 bge-m3 ----
        if conf.EMBEDDING_URL:
            self.embedding_function = RemoteEmbeddings(
                conf.EMBEDDING_URL, conf.EMBEDDING_API_KEY,
                conf.EMBEDDING_MODEL, conf.EMBEDDING_DIM)
            self.has_sparse = False   # 远程只出稠密向量
            self.dense_dim = conf.EMBEDDING_DIM
            self.logger.info(f"嵌入模型：远程 {conf.EMBEDDING_MODEL}（{conf.EMBEDDING_URL}，仅稠密）")
        else:
            m3_path = os.path.join(rag_qa_path, 'bge-m3')
            self.embedding_function = BGEM3EmbeddingFunction(
                model_name_or_path=m3_path, use_fp16=(self.device == 'cuda'), device=self.device)
            self.has_sparse = True
            self.dense_dim = self.embedding_function.dim["dense"]
            self.logger.info(f"嵌入模型：本地 bge-m3（稠密+稀疏）")

        # ---- 重排序模型：配了远程 url 走 API，否则用本地 bge-reranker-large ----
        if conf.RERANK_URL:
            self.reranker = RemoteReranker(conf.RERANK_URL, conf.RERANK_API_KEY, conf.RERANK_MODEL)
            self.logger.info(f"重排序：远程 {conf.RERANK_MODEL}")
        else:
            reranker_path = os.path.join(rag_qa_path, 'bge-reranker-large')
            self.reranker = CrossEncoder(reranker_path, device=self.device)
            self.logger.info("重排序：本地 bge-reranker-large")

        # 初始化 Milvus 客户端，连接到指定主机和数据库
        self.client = MilvusClient(uri=f"http://{self.host}:{self.port}", db_name=self.database)
        # 调用方法创建或加载 Milvus 集合
        self._create_or_load_collection()

    # 类私有化方法
    def _create_or_load_collection(self):
        # 检查指定集合是否已经存在
        if not self.client.has_collection(self.collection_name):
            # 创建集合 Schema，禁用自动 ID，启用动态字段
            schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
            # 添加 ID 字段，作为主键，VARCHAR 类型，最大长度 100
            schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=100)
            # 添加文本字段，VARCHAR 类型，最大长度 65535
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            # 添加稠密向量字段，FLOAT_VECTOR 类型，维度由嵌入函数指定
            schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=self.dense_dim)
            # 添加稀疏向量字段，SPARSE_FLOAT_VECTOR 类型
            schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
            # 添加父块 ID 字段，VARCHAR 类型，最大长度 100
            schema.add_field(field_name="parent_id", datatype=DataType.VARCHAR, max_length=100)
            # 添加父块内容字段，VARCHAR 类型，最大长度 65535
            schema.add_field(field_name="parent_content", datatype=DataType.VARCHAR, max_length=65535)
            # 添加主题类别字段，VARCHAR 类型，最大长度 50
            schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=50)
            # 添加文档级 ID 字段：同一文件的全部块共享，稳定跨批次，用于按文档删除/去重/详情
            schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=100)
            # 添加文档标题字段（文件名去扩展名），供前端列表与引用溯源直接展示
            schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=255)
            # 添加来源文件路径字段，删除文档时可定位磁盘文件
            schema.add_field(field_name="file_path", datatype=DataType.VARCHAR, max_length=1024)
            # 添加时间戳字段，VARCHAR 类型，最大长度 50
            schema.add_field(field_name="timestamp", datatype=DataType.VARCHAR, max_length=50)

            # 创建索引参数对象
            index_params = self.client.prepare_index_params()
            # 为稠密向量字段添加 IVF_FLAT 索引，度量类型为内积 (IP)
            index_params.add_index(
                field_name="dense_vector",
                index_name="dense_index",
                index_type="IVF_FLAT",
                metric_type="IP",
                params={"nlist": 128}
            )
            # 为稀疏向量字段添加 SPARSE_INVERTED_INDEX 索引，度量类型为内积 (IP)
            index_params.add_index(
                field_name="sparse_vector",
                index_name="sparse_index",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.2}
            )

            # 创建 Milvus 集合，应用定义的 Schema 和索引参数
            self.client.create_collection(collection_name=self.collection_name, schema=schema,
                                          index_params=index_params)
            # 记录创建集合的日志
            logger.info(f"已创建集合 {self.collection_name}")
        # 如果集合已存在
        else:
            # 记录加载集合的日志
            logger.info(f"已加载集合 {self.collection_name}")
        # 将集合加载到内存，确保可立即查询
        self.client.load_collection(self.collection_name)

    # 定义方法，向向量存储添加文档
    def add_documents(self, documents):
        # print(f'documents--》{documents[0]}')
        # 提取所有文档的内容列表
        texts = [doc.page_content for doc in documents]

        # 使用 BGE-M3 嵌入函数生成文档的嵌入
        embeddings = self.embedding_function(texts)
        # print(f'embeddings--》{embeddings}')
        # print(f'embeddings--》{embeddings.keys()}')
        # 初始化空列表，存储插入的数据
        data = []
        # 同一批次内重复块主键（相同内容哈希的重复块）Milvus 会拒绝：
        # MilvusException code=1100 duplicate primary keys。重复内容块纯属冗余，
        # 这里按 id 去重后再组成批次。
        seen_ids = set()
        # 遍历每个文档，带上索引i
        for i, doc in enumerate(documents):
            # 生成文档内容的哈希值作为唯一的ID
            text_hash = hashlib.md5(doc.page_content.encode('utf-8')).hexdigest()
            if text_hash in seen_ids:
                continue
            seen_ids.add(text_hash)
            # print(f'text_hash--》{text_hash}')
            # print(f'text_hash--》{type(text_hash)}')
            # 初始化一个稀疏向量的字典（Milvus要求存储稀疏向量的格式）
            sparse_vector = {}
            # 远程嵌入只出稠密向量（sparse 为 None），此时稀疏字段存空，检索端据此降级
            if embeddings["sparse"] is not None:
                # BGE-M3 的稀疏向量是 scipy csr_array（形状 n_docs x vocab）。
                # 新版 scipy 的 csr_array 没有 .getrow() 方法，单行索引又会返回类型不稳定的
                # coo_array，因此这里直接用 CSR 的 indptr/indices/data 三件套切出第 i 行，
                # 兼容新旧版本 scipy。
                sp_indices = embeddings["sparse"].indices
                sp_indptr = embeddings["sparse"].indptr
                sp_values = embeddings["sparse"].data
                # 第 i 行的非零列下标位于 [indptr[i], indptr[i+1]) 区间
                for pos in range(sp_indptr[i], sp_indptr[i + 1]):
                    sparse_vector[sp_indices[pos]] = sp_values[pos]
            # print(f'sparse_vector--》{sparse_vector}')
            # print(f'sparse_vector--》{len(sparse_vector)}')
            # print(embeddings["dense"][i])
            # print(embeddings["dense"][i].shape)
            # 创建数据字典，包含所有字段
            data.append({
                "id": text_hash,
                "text": doc.page_content,
                "dense_vector": embeddings["dense"][i],
                "sparse_vector": sparse_vector,
                "parent_id": doc.metadata["parent_id"],
                "parent_content": doc.metadata["parent_content"],
                "source": doc.metadata.get("source", "unknown"),
                "doc_id": doc.metadata.get("doc_id", ""),
                "title": doc.metadata.get("title", ""),
                "file_path": doc.metadata.get("file_path", ""),
                "timestamp": doc.metadata.get("timestamp", "unknown")
            })
        # 检查是否有数据需要插入
        if data:
            # 稀疏向量按 id 出现顺序收集在 data 里，此处无需重排（上面已同步跳过去重项）
            # 使用 upsert 操作插入数据，覆盖重复 ID
            self.client.upsert(collection_name=self.collection_name, data=data)
            # 记录插入或更新的文档数量日志
            logger.info(f"已插入或更新 {len(data)} 个文档")

    # 定义方法，执行混合检索并重排序
    def hybrid_search_with_rerank(self, query, k=conf.RETRIEVAL_K, source_filter=None) -> list[dict]:
        # 使用 BGE-M3 嵌入函数生成查询的嵌入
        query_embeddings = self.embedding_function([query])
        # 获取查询的稠密向量
        dense_query_vector = query_embeddings["dense"][0]
        # print(f'dense_query_vector--》{dense_query_vector.shape}')
        # 初始化过滤表达式，默认不过滤
        filter_expr = f"source == '{source_filter}'" if source_filter else ""
        # 创建稠密向量搜索请求
        dense_request = AnnSearchRequest(
            data=[dense_query_vector],
            anns_field="dense_vector",
            param={"metric_type": "IP", "params": {"nprobe": 10}},
            limit=k,
            expr=filter_expr
        )
        # sparse 是否为 None 决定是否走「稠密+稀疏」混合：
        # 本地 bge-m3 有稀疏向量 → 全量混合；远程嵌入只出稠密 → 退化为纯稠密检索。
        has_sparse = query_embeddings["sparse"] is not None
        if has_sparse:
            # 初始化查询的稀疏向量字典
            sparse_query_vector = {}
            # 查询稀疏向量是 scipy csr_array（形状 1 x vocab），新版 scipy 没有 .getrow()，
            # 查询只有一行，直接用 CSR 的 indices/data 属性取全部非零值即可。
            indices = query_embeddings["sparse"].indices
            values = query_embeddings["sparse"].data
            # 将索引和值配对，填充稀疏向量字典
            for idx, value in zip(indices, values):
                sparse_query_vector[idx] = value
            # 创建稀疏向量搜索请求
            sparse_request = AnnSearchRequest(
                data=[sparse_query_vector],
                anns_field="sparse_vector",
                param={"metric_type": "IP", "params": {}},
                limit=k,
                expr=filter_expr
            )
            # 加权排序器：稀疏 0.7，稠密 1.0
            ranker = WeightedRanker(1.0, 0.7)
            reqs = [dense_request, sparse_request]
        else:
            # 仅稠密检索：单路搜索
            ranker = WeightedRanker(1.0)
            reqs = [dense_request]
        # 执行混合搜索，返回 Top-K 结果
        results = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=reqs,
            ranker=ranker,
            limit=k,
            output_fields=["text", "parent_id", "parent_content", "source", "doc_id", "title", "timestamp"]
        )[0]
        # print(f'results--》{results}')
        # print(f'results--》{type(results)}')
        # print(f'results--》{len(results)}')
        # 将上述搜索到的结果进行Document对象封装，便于查询使用
        sub_chunks = [self._doc_from_hit(hit["entity"])for hit in results]
        # print(f'sub_chunks--》{len(sub_chunks)}')
        # 从子块中提取去重的父文档
        parent_docs = self._get_unique_parent_docs(sub_chunks)
        # print(f'parent_docs--》{parent_docs}')
        # print(f'parent_docs--》{len(parent_docs)}')
        # # 如果只有1个文档或者没有，直接返回跳过重排序
        if len(parent_docs) < 2:
            return parent_docs[:conf.CANDIDATE_M]
            # 如果有父文档，进行重排序
        if parent_docs:
            # 创建查询与文档内容的配对列表
            pairs = [[query, doc.page_content] for doc in parent_docs]
            # 使用 BGE-Reranker 计算每个配对的得分
            scores = self.reranker.predict(pairs)
            # print(f'scores--》{scores}')
            # 根据得分从高到低排序文档
            ranked_parent_docs = [doc for _, doc in sorted(zip(scores, parent_docs), reverse=True)]
        # 如果没有父文档，返回空列表
        # 如果没有父文档，返回空列表
        else:
            ranked_parent_docs = []

        # 返回前 m 个重排序后的文档
        return ranked_parent_docs[:conf.CANDIDATE_M]

    def _get_unique_parent_docs(self, sub_chunks):
        # 初始化集合，用于存储已处理的父块内容（去重）
        parent_contents = set()
        # 初始化列表，用于存储唯一父文档
        unique_docs = []
        # 遍历所有子块
        for chunk in sub_chunks:
            # 获取子块的父块内容，默认为子块内容
            parent_content = chunk.metadata.get("parent_content", chunk.page_content)
            # 检查父块内容是否非空且未重复
            if parent_content and parent_content not in parent_contents:
                # 创建新的 Document 对象，包含父块内容和元数据
                unique_docs.append(Document(page_content=parent_content, metadata=chunk.metadata))
                # 将父块内容添加到去重集合
                parent_contents.add(parent_content)
            # 返回去重后的父文档列表
        return unique_docs

    # 定义类似私有方法，从 Milvus 查询结果创建 Document 对象
    def _doc_from_hit(self, hit):
        # 创建并返回 Document 对象，填充内容和元数据
        return Document(
            page_content=hit.get("text"),
            metadata={
                "parent_id": hit.get("parent_id"),
                "parent_content": hit.get("parent_content"),
                "source": hit.get("source"),
                "doc_id": hit.get("doc_id"),
                "title": hit.get("title"),
                "timestamp": hit.get("timestamp")
            }
        )

    # ============================================================
    # 知识库浏览/文档管理 —— 基于文档级元数据（doc_id/title）聚合
    # ============================================================

    @staticmethod
    def _doc_filter(subject=None):
        """拼接知识库查询的标量过滤表达式。subject 可选。"""
        return f'source == "{subject}"' if subject else ""

    def _query_chunks(self, subject=None, doc_id=None, q=None, limit=None):
        """查询块级数据，返回原始行列表。按 subject / doc_id / q(正文 LIKE) 过滤。"""
        expr_parts = []
        if subject:
            expr_parts.append(f'source == "{subject}"')
        if doc_id:
            expr_parts.append(f'doc_id == "{doc_id}"')
        if q:
            expr_parts.append(f'text like "%{q}%"')
        expr = " and ".join(expr_parts) if expr_parts else None
        kwargs = dict(
            collection_name=self.collection_name,
            output_fields=["id", "text", "parent_id", "parent_content", "source", "doc_id", "title", "file_path", "timestamp"],
            # Milvus 空表达式必须带 limit（上限 16384），否则直接 500
            limit=limit or 16000,
        )
        if expr:
            kwargs["filter"] = expr
        return self.client.query(**kwargs)

    def list_documents(self, subject=None, q=None) -> list[dict]:
        """列出知识库文档（按 doc_id 聚合块）。返回 DocSummary 列表见 docs/API.md §4。"""
        rows = self._query_chunks(subject=subject, q=q)
        docs = {}
        for r in rows:
            doc_id = r.get("doc_id") or r.get("parent_id") or r.get("id")
            p = docs.setdefault(doc_id, {
                "id": doc_id,
                "title": r.get("title") or f"文档片段{len(docs) + 1}",
                "subject": r.get("source", "未知"),
                "updated_at": r.get("timestamp", ""),
                "chunk_count": 0,
            })
            p["chunk_count"] += 1
            if not p["updated_at"]:
                p["updated_at"] = r.get("timestamp", "")
        return list(docs.values())

    def list_sources(self) -> list:
        """返回知识库中已存在的全部主题（source 字段去重），作为动态分类来源。

        "已有数据的保留"：只要库里还有某主题的块，它就会出现在这里；
        上传到新主题后，新主题也随之上浮。查询失败时返回空列表，不抛异常。

        说明：不用 pymilvus 的 query_distinct（部分版本缺失），改 query 全字段拉回后内存去重，全版本兼容。
        """
        try:
            rows = self.client.query(
                collection_name=self.collection_name,
                output_fields=["source"],
                limit=16000,
            )
            return sorted({r.get("source") for r in rows if r.get("source")})
        except Exception as e:
            self.logger.error(f"查询主题列表失败: {e}")
            return []

    def get_document(self, doc_id: str) -> dict:
        """取单个文档详情（含全文 + 有序块列表），不存在返回 None。"""
        rows = self._query_chunks(doc_id=doc_id)
        if not rows:
            return None
        # 用父块拼接全文：parent_id 形如 doc_{i}_parent_{j}，按 j 保序去重
        parents = {}
        for r in rows:
            pid = r.get("parent_id")
            if pid and pid not in parents:
                parents[pid] = r.get("parent_content") or r.get("text")
        ordered = sorted(parents.items(), key=lambda kv: self._parent_order(kv[0]))
        title = rows[0].get("title") or f"文档{r.get('parent_id', doc_id)[:8] if (r := rows[0]) else doc_id}"
        return {
            "id": doc_id,
            "title": title,
            "subject": rows[0].get("source", "未知"),
            "updated_at": rows[0].get("timestamp", ""),
            "chunk_count": len(rows),
            "content": "\n\n".join(text for _, text in ordered),
            "chunks": [{"id": r.get("id"), "text": r.get("text"),
                        "parent_id": r.get("parent_id"),
                        "parent_content": r.get("parent_content") or r.get("text")} for r in rows],
        }

    def search_documents(self, query: str, subject=None, k=10) -> list[dict]:
        """库内语义/关键词混合搜索，返回按文档聚合的 Results（见 docs/API.md §6.5）。

        v1 用正文 LIKE 做关键词匹配（标量检索），按 doc_id 聚合给出首块摘要。
        后续可换成 hybrid_search 带距离分。

        Args:
            query: 搜索关键词。
            subject: 可选主题过滤。
            k: 聚合后最多返回的文档数。
        """
        rows = self._query_chunks(subject=subject, q=query)
        docs = {}
        for r in rows:
            doc_id = r.get("doc_id") or r.get("parent_id") or r.get("id")
            p = docs.setdefault(doc_id, {
                "doc_id": doc_id,
                "title": r.get("title") or f"文档片段{len(docs) + 1}",
                "snippet": r.get("text", "")[:80],
                "score": None,
            })
            if not p["snippet"]:
                p["snippet"] = r.get("text", "")[:80]
        return list(docs.values())[:k]

    @staticmethod
    def _parent_order(parent_id: str) -> int:
        """从 parent_id（doc_0_parent_5）解析父块序号，用于全文排序。"""
        try:
            return int(parent_id.rsplit("_parent_", 1)[-1])
        except (ValueError, AttributeError, IndexError):
            return 0

    def delete_document(self, doc_id: str) -> int:
        """按文档删除所有块，返回删除条数。"""
        res = self.client.delete(collection_name=self.collection_name,
                                 filter=f'doc_id == "{doc_id}"')
        return res.get("delete_count", 0)

    def document_file_paths(self, doc_id: str) -> set:
        """返回该文档在磁盘上的源文件路径（同文件的所有块路径一致，取一条即可）。"""
        rows = self._query_chunks(doc_id=doc_id, limit=1)
        return {r.get("file_path") for r in rows if r.get("file_path")}
if __name__ == "__main__":
    vector_store = VectorStore()
    # vector_store._create_or_load_collection()
    # 用脚本所在目录推导绝对路径，避免依赖启动时的工作目录（cwd）
    # directory_path = os.path.join(rag_qa_path, 'data', 'ai_data')
    # print(f"embedding_function.dim--》{vector_store.embedding_function.dim}")
    # documents = process_documents(directory_path)
    # vector_store.add_documents(documents)
    query = "AI主题的课程内容是什么"
    results = vector_store.hybrid_search_with_rerank(query, source_filter='ai')
    print(f'results-->{results}')
    print(f'results-->{type(results)}')
    print(f'results-->{len(results)}')