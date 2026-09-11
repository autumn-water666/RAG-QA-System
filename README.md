# RAG 智慧问答系统

通用智能问答系统。用 **LangGraph 状态机编排**把「路由 → 问题解析 → BM25 快速命中 → 向量混合召回 → LLM 生成」串成一条可观测的流水线，支持流式输出、多轮对话、引用溯源，以及知识库的在线浏览/上传/删除/重建。

## 架构

```
用户问题（WebSocket /api/stream）
   │
   ▼
┌────────────────────────────────────────────┐
│ LangGraph 编排图（rag_qa/core/graph.py）      │
│                                            │
│  START ─► classify（意图识别，可关）           │
│             │ 通用知识 » generate（直接 LLM）  │
│             └ 专业咨询 » analyze（问题解析）   │
│                            │ 规范查询+选策略  │
│                            ▼                │
│                   bm25（MySQL 快速命中）       │
│                      │ 命中 » generate       │
│                      │      （LLM 仲裁标准答案）│
│                      │ 未命中&需RAG           │
│                      ▼                      │
│                   retrieve（混合召回）         │
│                            │                │
│                            ▼                │
│                   generate（LLM 生成答案）     │
│                            │                │
│                            └► END（带引用溯源）│
└────────────────────────────────────────────┘
```

- **classify** — BERT 查询分类器，判断"通用知识"（不用检索直答 LLM）还是"专业咨询"（走检索）。可通过设置页运行时开关，关闭后所有问题一律走检索。
- **analyze** — 一次 LLM 调用同时产出"规范查询"（去口语化/纠错/补全）+ "检索策略"，让 BM25 与向量检索都按好问题匹配。
- **bm25** — MySQL 问题语料上的 rank_bm25 快速命中，softmax 归一化后按阈值（默认 0.92）判定。命中不硬返回，而是把标准答案降级为"证据上下文"交给 LLM 仲裁，防过时/误配。
- **retrieve** — Milvus 混合召回（BGE-M3 稠密 + 稀疏向量）+ Reranker 重排，用 analyze 预设的策略执行，不重复调 LLM。
- **generate** — 拼上下文送 LLM 逐 token 流式产出，结束帧携带引用溯源 `sources` 供前端渲染"参考来源"。

## 技术栈

| 组件 | 技术 |
|------|------|
| 编排 | LangGraph（StateGraph 状态机） |
| 意图识别 | BERT 查询分类器（可运行时开关） |
| BM25 快速命中 | MySQL 问题语料 + rank_bm25 + Redis 缓存 |
| 向量检索 | Milvus + BGE-M3（稠密 + 稀疏混合召回） |
| 重排序 | BGE-Reranker |
| 嵌入 / 重排模型 | 远程 OpenAI 兼容 API（SiliconFlow 等），留空则回退本地模型 |
| LLM | Mimo / DashScope（OpenAI 兼容接口） |
| 检索策略 | LLM 自动选择（HyDE / 子查询 / 回溯 / 直接检索） |
| Web 框架 | FastAPI + WebSocket（流式）+ REST（非流式） |
| 前端 | React 18 + Vite（HashRouter，双主题） |

> **远程嵌入/重排**：在 `config.ini` 的 `[models]` 里配 `embedding_url` / `rerank_url` + API Key + 模型名即走远程；留空则用本地 `bge-m3` / `bge-reranker-large`。注意远程嵌入只有稠密向量，稀疏检索会随之降级为纯稠密。

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+、Redis、Milvus 2.x
- LLM API Key（Mimo / DashScope），以及可选的 SiliconFlow Key（远程嵌入/重排）

### 2. 安装依赖

```bash
cd integrated_qa_system
pip install -r requirments.txt
```

### 3. 配置

编辑 [integrated_qa_system/config.ini](integrated_qa_system/config.ini)（**已 gitignore、不入版本库**，含密钥）：

```ini
[mysql]
host = localhost
user = root
password = 你的密码
database = subjects_kg

[llm]
model_name = mimo-v2.5
llm_base_url = https://api.xiaomimimo.com/v1
llm_api_key = 你的Mimo/LLM Key

[models]              # 留空 url 则回退本地 bge-m3 / bge-reranker-large
embedding_url = https://api.siliconflow.cn/v1
embedding_api_key = 你的SiliconFlow Key
embedding_model = BAAI/bge-m3
rerank_url = https://api.siliconflow.cn/v1
rerank_api_key = 你的SiliconFlow Key
rerank_model = BAAI/bge-reranker-v2-m3
```

常用开关（均在 `[app]` / `[retrieval]`）：

| 配置项 | 作用 |
|--------|------|
| `use_intent_classify` | 意图识别开关，true=按通用/专业路由，false=一律走检索（设置页可运行时切换） |
| `bm25_threshold` | BM25 快速命中置信度阈值，越高越保守（默认 0.92，只放非常高置信的标准问答） |
| `valid_sources` | （可选）主题初始种子，逗号分隔。缺省留空 = 分类完全由知识库已有数据 / 上传产生 |
| `retrieval_k` / `candidate_m` | 混合召回候选子块数 / 重排后返回父块数 |

### 4. 初始化与灌库

```bash
# 建 MySQL conversation 表（会话历史，应用启动时也会自动建）
# 切分文档 → 向量化 → 写入 Milvus（也可在知识库页面上传/重建）
python rag_qa/rag_main.py --data-processing --data-dir rag_qa/data
```

### 5. 前端构建（改动样式后）

```bash
cd frontend
npm run build      # 产物输出到 static/，由 FastAPI 根挂载托管，刷新即生效
```

### 6. 启动服务

```bash
# 后端（生产端口 8000，与 deploy.sh 一致）
cd integrated_qa_system
uvicorn app:app --host 0.0.0.0 --port 8000
# 或直接 python app.py（默认 8001，仅直跑调试用）
```

启动后打开 `http://localhost:8000`（或前端 `npm run dev` 走 5173 代理）。

### 7. 部署（手动 deploy.sh）

推送后一键同步：

```bash
bash deploy.sh    # git pull → 前端有改动则 npm build → 后端有改动则按端口重启 uvicorn
```

纯"推了就同步"，不上服务/Webhook/Docker。`PORT=8080 bash deploy.sh` 可覆盖后端端口（默认 8000）。

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| WS | `/api/stream` | 流式问答（帧：`start`/`token`/`end`/`error`，`end` 带引用溯源 `sources`） |
| POST | `/api/query` | 非流式：日常问候 / BM25 命中直答，命中率低则提示走 WebSocket |
| GET | `/api/settings/intent` · POST | 查询 / 运行时切换意图识别开关 |
| GET/POST/DELETE | `/api/kb/documents` | 知识库文档列表 / 上传 / 删除 |
| POST | `/api/kb/rebuild` | 全量重建向量索引（幂等） |
| GET | `/api/sources` · `/api/sessions` | 主题列表 · 会话列表 |

完整契约见 [docs/API.md](docs/API.md)。

## 项目结构

```
integrated_qa_system/
├── app.py                  # FastAPI 入口（REST + WebSocket + 静态托管）
├── new_main.py             # IntegratedQASystem（会话/历史/图编排）
├── config.ini              # 系统配置（gitignore，不入库）
├── base/                   # Config + logger
├── mysql_qa/               # MySQL 会话历史 + Redis 缓存 + BM25（rank_bm25）
├── rag_qa/
│   ├── core/
│   │   ├── graph.py            # LangGraph 编排层
│   │   ├── rag_system.py       # 检索合并 + LLM 生成
│   │   ├── vector_store.py     # Milvus 混合检索 + Reranker
│   │   ├── query_classifier.py # BERT 查询分类器
│   │   ├── strategy_selector.py # 问题解析(analyze) + 检索策略
│   │   ├── prompts.py          # Prompt 模板
│   │   └── document_processor.py # 文档切分
│   └── data/                   # {主题}_data/ 文档源文件
├── frontend/               # React 源码（Vite）
├── static/                 # 前端构建产物（FastAPI 托管）
└── logs/                   # 运行日志
```

## 检索策略

LLM 在 analyze 阶段为每次查询自动选择最适合的向量检索增强策略：

- **直接检索**：查询意图明确，直接用（规范）查询向量检索
- **假设问题检索（HyDE）**：LLM 先生成假设答案，再用假设答案检索
- **子查询检索**：复杂查询拆分为多个子查询，分别检索后合并
- **回溯问题检索**：将复杂/口语化问题简化为基础问题后再检索

## 文档

- [docs/API.md](docs/API.md) — 接口契约
- [docs/DEV.md](docs/DEV.md) — 开发文档

## License

MIT