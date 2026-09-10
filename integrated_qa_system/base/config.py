# -*- coding:utf-8 -*-
# 导入配置ini文件的解析库
import configparser
# 导入路径操作
import os
# 获取当前文件的绝对路径
current_file_path = os.path.abspath(__file__)
# print(f'current_file_path--》{current_file_path}')
# 获取当前文件所在目录的绝对路径
current_dir_path = os.path.dirname(current_file_path)
# print(f'current_dir_path--》{current_dir_path}')
# 获取项目根目录的绝对路径
project_root = os.path.dirname(current_dir_path)

config_file_path = os.path.join(project_root, 'config.ini')
# print(f'config_file_path--》{config_file_path}')

class Config():
    def __init__(self, config_file=config_file_path):
        # config_file代表配置文件ini的路径
        # 1.创建配置文件解析器
        self.config = configparser.ConfigParser()
        # 2. 读取配置文件（config.ini 为 UTF-8 编码，须显式指定，否则 Windows 默认用 GBK 解码会报错）
        self.config.read(config_file, encoding="utf-8")
        # 3. 获取相关的配置
        # 3.1 获取Mysql数据库的配置
        # mysql的主机地址
        # self.MYSQL_HOST = self.config["mysql"]["host1"]
        # fallback如果键不存在，这就是充当默认值
        self.MYSQL_HOST = self.config.get('mysql', 'host', fallback='localhost')
        # MySQL 用户名
        self.MYSQL_USER = self.config.get('mysql', 'user', fallback='root')
        # MySQL 密码
        self.MYSQL_PASSWORD = self.config.get('mysql', 'password', fallback='123456')
        # MySQL 数据库名
        self.MYSQL_DATABASE = self.config.get('mysql', 'database', fallback='subjects_kg')

        # Redis 配置
        # Redis 主机地址
        self.REDIS_HOST = self.config.get('redis', 'host', fallback='localhost')
        # Redis 端口
        self.REDIS_PORT = self.config.getint('redis', 'port', fallback=6379)
        # Redis 密码
        self.REDIS_PASSWORD = self.config.get('redis', 'password', fallback='1234')
        # Redis 数据库编号
        self.REDIS_DB = self.config.getint('redis', 'db', fallback=0)
        # 日志文件路径
        self.LOG_FILE = self.config.get('logger', 'log_file', fallback='logs/app.log')

        # 文本切分配置
        self.PARENT_CHUNK_SIZE = self.config.getint('chunking', 'parent_chunk_size', fallback=1500)
        self.CHILD_CHUNK_SIZE = self.config.getint('chunking', 'child_chunk_size', fallback=500)
        self.CHUNK_OVERLAP = self.config.getint('chunking', 'chunk_overlap', fallback=200)

        # Milvus 向量数据库配置
        # 向量数据库主机地址
        self.MILVUS_HOST = self.config.get('milvus', 'host', fallback='localhost')
        # 向量数据库端口
        self.MILVUS_PORT = self.config.getint('milvus', 'port', fallback=19530)
        # 向量数据库名称
        self.MILVUS_DATABASE_NAME = self.config.get('milvus', 'database_name', fallback='default')
        # 向量集合名称
        self.MILVUS_COLLECTION_NAME = self.config.get('milvus', 'collection_name', fallback='edu_rag')

        # 检索配置
        # 混合检索时取回的候选子块数量
        self.RETRIEVAL_K = self.config.getint('retrieval', 'retrieval_k', fallback=20)
        # 重排序后返回的父块数量
        self.CANDIDATE_M = self.config.getint('retrieval', 'candidate_m', fallback=5)
        # BM25 快速命中的置信度阈值(softmax 归一化后得分)。
        # 设高(默认0.92)= 只有非常高置信的标准问答才走快速直答，其余自然落到完整 RAG，
        # 兼顾"保留快通道"与高准确：调高降低误回标准答案的概率。
        self.BM25_THRESHOLD = self.config.getfloat('retrieval', 'bm25_threshold', fallback=0.92)

        # LLM 配置
        self.LLM_MODEL_NAME = self.config.get('llm', 'model_name', fallback='mimo-v2.5')
        self.LLM_BASE_URL = self.config.get('llm', 'llm_base_url', fallback='https://api.xiaomimimo.com/v1')
        self.LLM_API_KEY = self.config.get('llm', 'llm_api_key', fallback='no-key')

        # 嵌入模型配置（向量化）。embedding_url 非空 → 走远程 OpenAI 兼容 /embeddings；
        # 留空 → 用本地 bge-m3。远程接口只返回稠密向量，稀疏检索随之降级（见 vector_store）。
        self.EMBEDDING_URL = self.config.get('models', 'embedding_url', fallback='')
        self.EMBEDDING_API_KEY = self.config.get('models', 'embedding_api_key', fallback='')
        self.EMBEDDING_MODEL = self.config.get('models', 'embedding_model', fallback='BAAI/bge-m3')
        self.EMBEDDING_DIM = self.config.getint('models', 'embedding_dim', fallback=1024)

        # 重排序模型配置。rerank_url 非空 → 走远程 /rerank（Cohere 兼容返回）；
        # 留空 → 用本地 bge-reranker-large。
        self.RERANK_URL = self.config.get('models', 'rerank_url', fallback='')
        self.RERANK_API_KEY = self.config.get('models', 'rerank_api_key', fallback='')
        self.RERANK_MODEL = self.config.get('models', 'rerank_model', fallback='BAAI/bge-reranker-v2-m3')

        # 其他配置
        self.CUSTOMER_SERVICE_PHONE = self.config.get('app', 'customer_service_phone', fallback='12345678')
        # 意图识别（LangGraph classify 节点）开关：true=按"通用知识/专业咨询"路由；
        # false=跳过分类，所有问题一律走检索(RAG)。默认开启
        self.USE_INTENT_CLASSIFY = self.config.getboolean('app', 'use_intent_classify', fallback=True)
        # valid_sources 存的是逗号分隔字符串，转成真正可迭代的列表，
        # 否则下游 迭代/join/成员判断 都会拿整串字符串当列表用
        raw_sources = self.config.get('app', 'valid_sources', fallback='')
        self.VALID_SOURCES = [s.strip() for s in raw_sources.split(',') if s.strip()] \
            if raw_sources else ["ai", "java", "test", "ops", "bigdata"]



if __name__ == '__main__':
    config_file = 'integrated_qa_system/config.ini'
    conf = Config(config_file)
    print(conf.MYSQL_HOST)
    print(conf.LOG_FILE)