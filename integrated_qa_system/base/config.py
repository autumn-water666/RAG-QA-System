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

        # LLM 配置
        self.LLM_MODEL_NAME = self.config.get('llm', 'model_name', fallback='mimo-v2.5')
        self.DASHSCOPE_BASE_URL = self.config.get('llm', 'dashscope_base_url', fallback='https://api.xiaomimimo.com/v1')
        self.DASHSCOPE_API_KEY = self.config.get('llm', 'dashscope_api_key', fallback='no-key')

        # 其他配置
        self.CUSTOMER_SERVICE_PHONE = self.config.get('app', 'customer_service_phone', fallback='12345678')
        self.VALID_SOURCES = self.config.get('app', 'valid_sources', fallback=["ai", "java", "test", "ops", "bigdata"])



if __name__ == '__main__':
    config_file = 'integrated_qa_system/config.ini'
    conf = Config(config_file)
    print(conf.MYSQL_HOST)
    print(conf.LOG_FILE)