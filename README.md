# EduRAG 智慧问答系统

教育领域智能问答系统，结合 MySQL（BM25）+ Redis + Milvus（向量检索）多路召回，自动路由用户问题至 RAG 检索或直答 LLM，支持流式输出与多轮对话。

## 架构

```
用户问题
   │
   ▼
┌──────────────────────┐
│  BERT 查询分类器       │  判断问题类型
└──────┬───────┬───────┘
       │       │
  通用知识    专业咨询
       │       │
       ▼       ▼
    直接 LLM   BM25 + Milvus 混合检索
       │       │
       │    Reranker 重排序
       │       │
       ▼       ▼
     流式生成答案（FastAPI SSE / WebSocket）
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 向量数据库 | Milvus + BGE-M3 嵌入 |
| 重排序 | BGE-Reranker |
| BM25 | MySQL + Redis 缓存 |
| 查询分类 | BERT（bert-base-chinese 微调） |
| LLM | DashScope（通义千问） |
| 策略选择 | LLM 自动判断（HyDE / 子查询 / 回溯 / 直接检索） |
| Web 框架 | FastAPI + SSE / WebSocket |
| 前端 | React（Vite） |

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+
- Redis
- Milvus 2.x（或 Zilliz Cloud）
- DashScope API Key

### 2. 安装依赖

```bash
cd integrated_qa_system
pip install -r requirements.txt  # 若无 requirements.txt，手动安装核心包：
pip install pymilvus milvus-model sentence-transformers transformers torch
pip install fastapi uvicorn langchain langchain-openai openai pymysql redis
```

### 3. 配置

编辑 `config.ini`，填入数据库和 LLM 配置：

```ini
[mysql]
host = localhost
user = root
password = 你的密码
database = subjects_kg

[redis]
host = localhost
port = 6379

[milvus]
host = localhost
port = 19530
collection_name = edu_rag
```

同时设置环境变量：

```bash
export DASHSCOPE_API_KEY=你的API Key
```

### 4. 初始化 MySQL 表

```bash
cd integrated_qa_system/mysql_qa
python -c "
from db.mysql_client import MySQLClient
MySQLClient().create_table()
"
```

将教学数据导入 MySQL：

```python
mysql_client = MySQLClient()
mysql_client.insert_data(csv_path='rag_qa/data/数据.csv')
```

### 5. 灌入向量知识库

将文档放入对应目录（如 `rag_qa/data/ai_data/`），然后执行数据处理：

```bash
python rag_qa/rag_main.py --data-processing --data-dir rag_qa/data
```

### 6. 训练查询分类器（可选）

若 `rag_qa/bert_query_classifier/` 目录不存在，需先训练：

```bash
python -c "
from rag_qa.core.query_classifier import QueryClassifier
qc = QueryClassifier()
qc.train_model()
"
```

### 7. 启动服务

```bash
python app.py
```

启动后访问 http://localhost:8000 打开问答界面。

API 接口：

```bash
# SSE 流式查询
curl -N -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "AI课程大纲包含哪些内容？"}'

# WebSocket 流式查询
ws://localhost:8000/api/stream
```

## 项目结构

```
integrated_qa_system/
├── app.py                  # FastAPI 入口（SSE + WebSocket）
├── new_main.py             # 集成问答系统核心（IntegratedQASystem）
├── config.ini              # 系统配置
├── base/                   # 基础设施（配置、日志）
├── mysql_qa/               # MySQL + BM25 检索模块
│   ├── db/                 # MySQL 客户端
│   ├── cache/              # Redis 缓存
│   └── retrieval/          # BM25 搜索
├── rag_qa/                 # RAG 检索模块
│   ├── core/
│   │   ├── rag_system.py       # RAG 核心（检索 + 流式生成）
│   │   ├── vector_store.py     # Milvus 向量检索 + Rerank
│   │   ├── query_classifier.py # BERT 查询分类器
│   │   ├── strategy_selector.py # 检索策略选择器
│   │   ├── prompts.py          # Prompt 模板
│   │   └── document_processor.py # 文档处理
│   ├── edu_document_loaders/    # 教育文档加载器
│   ├── edu_text_spliter/        # 中文递归文本分割
│   ├── classify_data/           # 分类器训练数据
│   ├── bert_query_classifier/   # 训练好的分类器模型
│   └── rag_main.py              # 数据处理入口
└── static/                 # 前端静态文件
```

## 检索策略

系统通过 LLM 自动为每次查询选择最适合的检索增强策略：

- **直接检索**：查询意图明确，直接用原查询向量检索
- **假设问题检索（HyDE）**：LLM 先生成假设答案，再用假设答案检索
- **子查询检索**：复杂查询拆分为多个子查询，分别检索后合并
- **回溯问题检索**：将复杂问题简化为基础问题后再检索

## License

MIT
