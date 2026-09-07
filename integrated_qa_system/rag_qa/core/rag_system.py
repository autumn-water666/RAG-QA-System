# core/rag_system.py 源码
import os 
import sys

from langchain_openai import ChatOpenAI
# 路径设置：先把 rag_qa 和项目根目录加入 sys.path，再导入项目内模块（base.logger）。
# 否则从其他目录启动时 `from base import logger` 会 ImportError（与 core/vector_store.py 同样的问题）。
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/
sys.path.insert(0, rag_qa_path)
sys.path.insert(0, project_root)
sys.path.insert(0, current_dir)
from prompts import RAGPrompts
#   导入 time 模块，用于计算时间
import time
from base import logger, Config
from query_classifier import QueryClassifier  #   导入查询分类器
from strategy_selector import StrategySelector  #   导入策略选择器
from vector_store import VectorStore  #   导入向量数据库类

conf = Config()

#   定义 RAGSystem 类，封装 RAG 系统的核心逻辑
class RAGSystem:
    #   初始化方法，设置 RAG 系统的基本参数
    def __init__(self, vector_store, llm):
        #   设置向量数据库对象
        self.vector_store = vector_store
        #   设置大语言模型调用函数
        self.llm = llm
        #   获取 RAG 提示模板
        self.rag_prompt = RAGPrompts.rag_prompt()
        #   初始化查询分类器（不传 model_path 用默认路径 rag_qa/bert_query_classifier，
        #   与 query_classifier.py 训练时的保存位置一致，避免路径差一层导致找不到模型）
        self.query_classifier = QueryClassifier()
        #   初始化策略选择器
        self.strategy_selector = StrategySelector()

    def _call_llm_text(self, prompt) -> str:
        """调用 LLM 并拼接为完整字符串，兼容两种 llm：
        一次性返回字符串的普通函数，以及按 token 产出的流式生成器。"""
        result = self.llm(prompt)
        if isinstance(result, str):
            return result
        if hasattr(result, "__iter__"):
            return "".join(str(token) for token in result)
        return str(result)

    #   定义私有方法，使用假设文档进行检索（HyDE）
    def _retrieve_with_hyde(self, query, source_filter=None):
        logger.info(f"使用 HyDE 策略进行检索 (查询: '{query}')")
        #   获取假设问题生成的 Prompt 模板
        hyde_prompt_template = RAGPrompts.hyde_prompt() # 使用 template 后缀区分
        #   调用大语言模型生成假设答案
        try:
            hypo_answer = self._call_llm_text(hyde_prompt_template.format(query=query)).strip()
            logger.info(f"HyDE 生成的假设答案: '{hypo_answer}'")
            #   使用假设答案进行检索，并返回检索结果
            #   注意：HyDE 通常只用于生成检索向量，不一定需要 rerank 这一步，但这里复用了
            return self.vector_store.hybrid_search_with_rerank(
                hypo_answer, k=conf.RETRIEVAL_K ,source_filter=source_filter # 使用 K 而非 M
            )
        except Exception as e:
            logger.error(f"HyDE 策略执行失败: {e}")
            return []


    #   定义私有方法，使用子查询进行检索
    def _retrieve_with_subqueries(self, query, source_filter=None):
        logger.info(f"使用子查询策略进行检索 (查询: '{query}')")
        #   获取子查询生成的 Prompt 模板
        subquery_prompt_template = RAGPrompts.subquery_prompt() # 使用 template 后缀区分
        try:
            #   调用大语言模型生成子查询列表
            subqueries_text = self._call_llm_text(subquery_prompt_template.format(query=query)).strip()
            subqueries = [q.strip() for q in subqueries_text.split("\n") if q.strip()]
            logger.info(f"生成的子查询: {subqueries}")
            if not subqueries:
                 logger.warning("未能生成有效的子查询")
                 return []

            #   初始化空列表，用于存储所有子查询的检索结果
            all_docs = []
            #   遍历每个子查询
            for sub_q in subqueries:
                #   使用子查询进行检索，并将结果添加到列表中
                #   这里对每个子查询都执行了 hybrid search + rerank，开销可能较大
                docs = self.vector_store.hybrid_search_with_rerank(
                    sub_q, k=conf.CANDIDATE_M//2 ,source_filter=source_filter # 使用 K
                )
                all_docs.extend(docs)
                logger.info(f"子查询 '{sub_q}' 检索到 {len(docs)} 个文档")

            #   对所有检索结果进行去重 (基于对象内存地址，如果 Document 内容相同但对象不同则无法去重)
            #   更可靠的去重方式是基于文档内容或 ID
            unique_docs_dict = {doc.page_content: doc for doc in all_docs} # 基于内容去重
            unique_docs = list(unique_docs_dict.values())

            logger.info(f"所有子查询共检索到 {len(all_docs)} 个文档, 去重后剩 {len(unique_docs)} 个")
            #   返回去重后的文档，限制数量 (是否需要在此处限制? retrieve_and_merge 末尾会限制)
            # return unique_docs[: Config.CANDIDATE_M]
            return unique_docs # 返回所有唯一文档，让 retrieve_and_merge 处理数量

        except Exception as e:
            logger.error(f"子查询策略执行失败: {e}")
            return []

    #   定义私有方法，使用回溯问题进行检索
    def _retrieve_with_backtracking(self, query, source_filter=None):
        logger.info(f"使用回溯问题策略进行检索 (查询: '{query}')")
        #   获取回溯问题生成的 Prompt 模板
        backtrack_prompt_template = RAGPrompts.backtracking_prompt() # 使用 template 后缀区分
        try:
            #   调用大语言模型生成回溯问题
            simplified_query = self._call_llm_text(backtrack_prompt_template.format(query=query)).strip()
            logger.info(f"生成的回溯问题: '{simplified_query}'")
            #   使用回溯问题进行检索，并返回检索结果
            return self.vector_store.hybrid_search_with_rerank(
                simplified_query, k=conf.RETRIEVAL_K ,source_filter=source_filter
            )
        except Exception as e:
            logger.error(f"回溯问题策略执行失败: {e}")
            return []

    #   定义方法，检索并合并相关文档
    def retrieve_and_merge(self, query, source_filter=None, strategy=None):  #   新增 strategy 参数
        #   如果未指定检索策略，则使用策略选择器选择
        if not strategy:
            strategy = self.strategy_selector.select_strategy(query)

        #   根据检索策略选择不同的检索方式
        ranked_sub_chunks = [] # 初始化
        if strategy == "回溯问题检索":
            ranked_sub_chunks = self._retrieve_with_backtracking(query, source_filter=source_filter)
        elif strategy == "子查询检索":
            ranked_sub_chunks = self._retrieve_with_subqueries(query, source_filter=source_filter) # 返回的是唯一文档列表
             # 注意：子查询返回的是已 rerank 过的父文档或子块列表，后续合并逻辑可能需要调整
             # 当前实现中，子查询返回的是初步检索（可能已rerank）的块，再进行合并
        elif strategy == "假设问题检索":
            ranked_sub_chunks = self._retrieve_with_hyde(query, source_filter=source_filter)
        else:  #   默认或“直接检索”
            logger.info(f"使用直接检索策略 (查询: '{query}')")
            ranked_sub_chunks = self.vector_store.hybrid_search_with_rerank(
                query, k=conf.RETRIEVAL_K, source_filter=source_filter
            ) # 注意 hybrid_search_with_rerank 返回的是 rerank 后的父文档

        logger.info(f"策略 '{strategy}' 检索到 {len(ranked_sub_chunks)} 个候选文档 (可能已是父文档)")
        final_context_docs = ranked_sub_chunks[:conf.CANDIDATE_M]
        logger.info(f"最终选取 {len(final_context_docs)} 个文档作为上下文")
        return final_context_docs

    #   定义方法，流式生成答案
    def generate_answer(self, query, source_filter=None, history=None):
        """流式生成答案。

        Args:
            query: 用户问题。
            source_filter: 学科过滤条件。
            history: 对话历史，格式 [{"question":..., "answer":...}, ...]，用于多轮上下文。

        Yields:
            逐段产出的答案文本 token。
        """
        #   记录查询开始时间
        start_time = time.time()
        logger.info(f"开始处理查询: '{query}', 学科过滤: {source_filter}")

        #   将最近对话历史转成文本，并入上下文，让模型能看到多轮背景
        history_context = ""
        if history:
            history_context = "\n".join(
                f"用户: {item['question']}\n助手: {item['answer']}" for item in history
            )

        #   判断查询类型
        query_category = self.query_classifier.predict_category(query)
        logger.info(f"查询分类结果：{query_category} (查询: '{query}')")

        #   如果查询属于“通用知识”类别，直接使用 LLM 回答（不使用检索上下文）
        if query_category == "通用知识":
            logger.info("查询为通用知识，直接调用 LLM")
            context = history_context
        else:
            #   专业咨询：执行 RAG 检索
            logger.info("查询为专业咨询，执行 RAG 流程")
            #   选择检索策略
            strategy = self.strategy_selector.select_strategy(query)
            #   检索相关文档
            context_docs = self.retrieve_and_merge(
                query, source_filter=source_filter, strategy=strategy
            )
            #   准备上下文
            if context_docs:
                context = "\n\n".join([doc.page_content for doc in context_docs])
                logger.info(f"构建上下文完成，包含 {len(context_docs)} 个文档块")
            else:
                context = ""
                logger.info("未检索到相关文档，上下文为空")
            if history_context:
                context = f"对话历史:\n{history_context}\n\n当前检索到的上下文:\n{context}"

        #   构造 Prompt，调用大语言模型生成答案
        prompt_input = self.rag_prompt.format(
            context=context, question=query, phone=conf.CUSTOMER_SERVICE_PHONE
        )

        #   流式产出答案：兼容一次性返回字符串的 llm 与按 token 产出的流式生成器
        try:
            result = self.llm(prompt_input)
            if isinstance(result, str):
                yield result
            elif hasattr(result, "__iter__"):
                for token in result:
                    if token:
                        yield token
            else:
                yield str(result)
        except Exception as e:
            logger.error(f"调用 LLM 生成答案失败: {e}")
            yield f"抱歉，处理您的问题时出错。请联系人工客服：{conf.CUSTOMER_SERVICE_PHONE}"

        #   记录查询处理完成的日志
        processing_time = time.time() - start_time
        logger.info(f"查询处理完成 (耗时: {processing_time:.2f}s, 查询: '{query}')")

if __name__ == "__main__":
    #   测试 RAGSystem 类
    from vector_store import VectorStore  #   导入向量数据库类

    #   初始化向量数据库和大语言模型
    def llm(prompt):
        #这里可以替换为实际的 LLM 调用逻辑，例如调用 OpenAI API 或其他模型
        LLM=ChatOpenAI(
        model=conf.LLM_MODEL_NAME,
        base_url=conf.DASHSCOPE_BASE_URL,
        api_key=conf.DASHSCOPE_API_KEY,
        )
        response = LLM.invoke(prompt)
        return response.content.strip()
    vector_store = VectorStore()

    #   创建 RAGSystem 实例
    rag_system = RAGSystem(vector_store, llm)

    #   测试查询
    test_query = "什么是人工智能？"
    answer = "".join(rag_system.generate_answer(test_query))
    print(f"查询: {test_query}\n答案: {answer}")