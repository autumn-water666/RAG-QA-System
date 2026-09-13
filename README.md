# RAG 智慧问答系统

一个通用的智能问答系统。用 **LangGraph 状态机编排**把「意图识别 → 问题解析 → BM25 快速命中 → 向量混合召回 → LLM 生成」串成一条可观测的流水线,支持**流式输出、多轮对话、引用溯源**,以及知识库的**在线浏览 / 批量上传 / 删除 / 重建**。

> 通用领域无关设计:分类主题完全**数据驱动**,由知识库已有数据 / 用户上传产生,**没有硬编码默认分类**;领域从教育可平滑迁移到任意垂直场景。

## 核心特性

- **LangGraph 状态机编排**:逐个节点依次执行,每个节点职责单一、可单独替换/关闭,流程可观测。
- **运行时意图识别开关**:BERT 查询分类器判断「通用知识」(直答 LLM,不检索)还是「专业咨询」(走完整 RAG)。可在设置页**不重启服务**运行时切换,关闭后所有问题一律走检索。
- **问题解析(analyze)**:一次 LLM 调用同时产出「规范查询」(去口语化 / 纠错 / 补全)+「检索策略」,让 BM25 与向量检索都按高质量的问题去匹配,显著提升命中率。
- **BM25 快速命中 + LLM 仲裁**:MySQL 问题语料上的 `rank_bm25` 高置信命中不硬返回,而是把标准答案降级为"证据上下文"交给 LLM 仲裁(采纳 / 纠偏 / 拒答),防过时 / 误配。
- **向量混合召回 + 重排**:Milvus 上 BGE-M3 稠密 + 稀疏混合召回,再做 BGE-Reranker 重排;`analyze` 阶段自动选择检索增强策略(HyDE / 子查询 / 回溯 / 直接检索)。
- **流式输出 + 引用溯源**:逐 token SSE/WebSocket 流式生成,`end` 帧携带 `sources`,前端渲染「参考来源」卡片,`[N]` 角标与来源一一对应、可点击跳转。
- **知识库全生命周期管理**:浏览器端浏览文档详情 / 切块、多文件**批量上传**(后台异步处理,不阻塞事件循环)、删除并下索引、全量幂等重建。
- **会话隔离与续文追问**:按 `session_id` 隔离,支持携带上下文的多轮对话,也可关闭追问做独立单次提问。

## 架构

```
用户问题（WebSocket /api/stream）
   │
   ▼
┌─────────────────────────────────────────────┐
│ LangGraph 编排图（rag_qa/core/graph.py）      │
│                                             │
│  START ─► classify（意图识别，可运行时关闭）    │
│             │ 通用知识 » generate（直接 LLM）   │
│             └ 专业咨询 » analyze（问题解析）    │
│                            │ 规范查询 + 选策略  │
│                            ▼                 │
│                   bm25（MySQL 快速命中）        │
│                      │ 命中 » generate       │
│                      │      （LLM 仲裁标准答案）│
│                      │ 未命中 & 需 RAG        │
│                      ▼                       │
│                   retrieve（混合召回 + 重排）   │
│                            │                 │
│                            ▼                 │
│                   generate（LLM 流式生成答案）  │
│                            │                 │
│                            └► END（带引用溯源）│
└─────────────────────────────────────────────┘
```

流水线节点说明:

| 节点 | 文件 | 职责 |
|------|------|------|
| `classify` | `query_classifier.py` | BERT 查询分类器,判断「通用知识」(直答 LLM)还是「专业咨询」(走检索)。可通过设置页运行时开关,关闭后所有问题一律走检索。 |
| `analyze` | `strategy_selector.py` | 一次 LLM 调用同时产出「规范查询」(去口语化/纠错/补全)+「检索策略」,让后续检索按好问题匹配。 |
| `bm25` | `mysql_qa/` | MySQL 问题语料上的 `rank_bm25` 快速命中,softmax 归一化后按阈值(默认 0.92)判定;命中不硬返回,标准答案降级为"证据上下文"交给 LLM 仲裁。 |
| `retrieve` | `vector_store.py` | Milvus 混合召回(BGE-M3 稠密 + 稀疏)+ BGE-Reranker 重排,按 `analyze` 预设的策略执行,不重复调 LLM。 |
| `generate` | `rag_system.py` | 拼上下文送 LLM 逐 token 流式产出,`end` 帧携带引用溯源 `sources` 供前端渲染。 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 编排 | LangGraph(StateGraph 状态机) |
| 意图识别 | BERT 查询分类器(可运行时开关) |
| BM25 快速命中 | MySQL 问题语料 + `rank_bm25` + Redis 缓存 |
| 向量检索 | Milvus + BGE-M3(稠密 + 稀疏混合召回) |
| 重排序 | BGE-Reranker |
| 嵌入 / 重排模型 | 远程 OpenAI 兼容 API(SiliconFlow 等),留空则回退本地模型 |
| LLM | Mimo / DashScope(OpenAI 兼容接口) |
| 检索策略 | LLM 自动选择(HyDE / 子查询 / 回溯 / 直接检索) |
| Web 框架 | FastAPI + WebSocket(流式)+ REST(非流式) |
| 前端 | React 18 + Vite(HashRouter,双主题) |
| 开发工具 | Python 3.10+、uv/pip、Node 18+ |

> **远程嵌入/重排**:在 `config.ini` 的 `[models]` 里配置 `embedding_url` / `rerank_url` + API Key + 模型名即走远程;留空则用本地 `bge-m3` / `bge-reranker-large`。注意远程嵌入只有稠密向量,稀疏检索会随之降级为纯稠密。

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+(前端构建)
- **MySQL 8.0+**(会话历史 + BM25 语料)
- **Redis**(BM25 快速命中缓存)
- **Milvus 2.x**(向量检索,含配套 etcd)
- LLM API Key(Mimo / DashScope),以及可选的 SiliconFlow Key(远程嵌入/重排)

> 本地基础设施(Milvus / etcd / MySQL / Redis)可用 Docker Compose 一键拉起,详见 [docs/DEV.md](docs/DEV.md)「本地基础设施」一节。Milvus 默认**未开鉴权**。

### 2. 克隆仓库

```bash
git clone <your-repo-url> RAG
cd RAG
```

### 3. 安装依赖

依赖清单在**仓库根目录**的 `requirments.txt`(亦可用 `pyproject.toml` + `uv`,见 `uv.lock`):

```bash
# pip 方式
pip install -r requirments.txt

# 或 uv 方式（推荐，更快）
uv sync
```

前端依赖：

```bash
cd integrated_qa_system/frontend
npm install
```

### 4. 配置

编辑 [integrated_qa_system/config.ini](integrated_qa_system/config.ini)(**已 gitignore、不入版本库**,含各服务凭据与 API 密钥):

```ini
; ---- 数据源 ----
[mysql]                       ; 会话历史 + BM25 语料
host = localhost
user = root
password = 你的MySQL密码
database = subjects_kg

[redis]                       ; BM25 快速命中缓存
host = localhost
port = 6379
password = 1234
db = 0

[milvus]                      ; 向量检索
host = localhost
port = 19530
database_name = default
collection_name = edu_rag

; ---- 文本切分 ----
[chunking]
parent_chunk_size = 1500      ; 父块（重排/引用溯源粒度）
child_chunk_size = 500        ; 子块（检索粒度）
chunk_overlap = 200           ; 块间重叠，防止截断语义

; ---- LLM ----
[llm]
model_name = mimo-v2.5
llm_base_url = https://api.xiaomimimo.com/v1
llm_api_key = 你的Mimo/LLM Key

; ---- 嵌入 & 重排（url 留空则回退本地模型）----
[models]
embedding_url = https://api.siliconflow.cn/v1
embedding_api_key = 你的SiliconFlow Key
embedding_model = BAAI/bge-m3       ; 远程嵌入仅稠密向量
embedding_dim = 1024
rerank_url = https://api.siliconflow.cn/v1
rerank_api_key = 你的SiliconFlow Key
rerank_model = BAAI/bge-reranker-v2-m3

; ---- 应用行为 ----
[app]
#valid_sources =             ; （可选）初始主题种子，逗号分隔；缺省=分类完全由已有数据/上传产生
use_intent_classify = true   ; 意图识别开关：true=按通用/专业路由，false=一律走检索
CUSTOMER_SERVICE_PHONE = 12345678

[retrieval]
retrieval_k = 20              ; 混合召回候选子块数
candidate_m = 5               ; 重排后返回的父块数
bm25_threshold = 0.92         ; BM25 快速命中置信度阈值，越高越保守
```

**全部配置键速查**:

| 分区 | 键 | 说明 |
|------|----|------|
| `[mysql]` | host/user/password/database | 会话历史 + BM25 语料的 MySQL 连接 |
| `[redis]` | host/port/password/db | BM25 缓存,运行时需可用 |
| `[milvus]` | host/port/database_name/collection_name | 向量库连接与集合(库/集合需预先创建) |
| `[chunking]` | parent_chunk_size / child_chunk_size / chunk_overlap | 文档切分尺寸,决定检索粒度与引用溯源粒度 |
| `[retrieval]` | retrieval_k / candidate_m / bm25_threshold | 召回候选子块数 / 重排后父块数 / 快速命中阈值 |
| `[llm]` | model_name / llm_base_url / llm_api_key | 生成模型(OpenAI 兼容接口) |
| `[models]` | embedding_* / rerank_* | 嵌入与重排模型;url 留空回退本地 |
| `[app]` | valid_sources / use_intent_classify / CUSTOMER_SERVICE_PHONE | 主题种子、意图识别开关、客服电话 |

### 5. 初始化与灌库

```bash
# 文档切分 → 向量化 → 写入 Milvus
# （把原始文档放入 rag_qa/data/{subject}_data/，或直接在知识库页面批量上传）
python rag_qa/rag_main.py --data-processing --data-dir rag_qa/data
```

> MySQL 会话历史表(`conversations`)会在应用启动时自动创建,无需手动建表。

### 6. 前端构建(改动样式后)

```bash
cd integrated_qa_system/frontend
npm run build    # 产物输出到 ../static，由 FastAPI 根挂载托管，刷新即热更
```

### 7. 启动服务

```bash
cd integrated_qa_system

# 生产端口 8000（与 deploy.sh 一致）
uvicorn app:app --host 0.0.0.0 --port 8000

# 或直接 python app.py（默认 8001，仅本地直跑调试用）
python app.py
```

启动后打开 `http://localhost:8000`;前端开发时用 `npm run dev`(Vite 5173,已代理 `/api` 与 ws `/api/stream` 到 8000)。

### 8. 部署(手动 deploy.sh)

推送后一键同步,**不上服务 / Webhook / Docker**:

```bash
bash deploy.sh    # git pull → 前端有改动则 npm build → 后端有改动则按端口重启 uvicorn
```

- `PORT=8080 bash deploy.sh` 可覆盖后端端口(默认 8000)。
- deploy.sh 记录上次部署点(`.last_deploy`),增量判断前端/后端是否需构建/重启。
- 后端重启后约需 15 秒加载模型,可用 `curl http://localhost:PORT/health` 轮询可用性。

## 交互流程

```
UI 提问 ──ws──▶ /api/stream
   ▶ 服务端逐帧下发：start → token×N → end
   ▶ classify ▸ 通用知识 → generate（直接 LLM 生成）
                └ 专业咨询 → analyze（规范查询 + 选策略）
                              └▶ bm25 ──命中──▶ generate（LLM 仲裁标准答案）
                                       │ 未命中 & 需 RAG
                                       └▶ retrieve（按规范查询 + 预设策略混合召回 + 重排）
                                              └▶ generate（拼上下文流式生成）
   ▶ end 帧携带 sources（引用溯源）──▶ 前端渲染「参考来源」+ [N] 角标
```

- **续文追问**开:请求带 `session_id` ,携带上下文;关:`session_id` 传 `null`,独立提问不写历史。
- **引用溯源**:`retrieve` 节点持有带 `metadata` 的父文档列表,经 `_build_sources()` 映射为 `Source[]`(`index/title/subject/snippet/url`),url 指向 `#/kb/{parent_id}` 文档详情页。

## 接口

### 流式问答(核心)

`WS /api/stream` —— 单通道,一次连接一问一答。客户端发送:

```json
{ "query": "...", "source_filter": "ai|null", "session_id": "<uuid>|null" }
```

服务端四类帧:

```jsonc
{ "type": "start", "session_id": "..." }                    // 开始
{ "type": "token", "token": "...", "session_id": "..." }    // 流式 token（多次）
{ "type": "end", "is_complete": true, "processing_time": 2.3,
  "sources": [ { "index": 1, "title": "...", "subject": "ai",
                 "snippet": "...", "url": "#/kb/<parent_id>" } ] }  // 结束，带引用溯源
{ "type": "error", "error": "中文描述" }                     // 错误
```

### REST 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/create_session` | 创建会话(返回 `session_id`,前端存 localStorage 复用) |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/history/{session_id}` | 查询会话历史(最近 5 轮) |
| DELETE | `/api/history/{session_id}` | 清除会话历史 |
| GET | `/api/sources` | 主题列表(数据驱动:磁盘目录 + Milvus + 可选种子) |
| WS | `/api/stream` | 流式问答(上节) |
| POST | `/api/query` | 非流式查询(兼容保留,前端不再调用) |
| GET | `/api/kb/documents?subject=&q=` | 知识库文档列表(按主题过滤 / 关键词搜索) |
| GET | `/api/kb/documents/{doc_id}` | 文档详情(全文 + 有序切块) |
| POST | `/api/kb/documents` | 批量上传(multipart,异步返回 job_id) |
| GET | `/api/kb/uploads/{job_id}` | 上传任务进度(轮询) |
| GET | `/api/kb/search?q=&subject=` | 库内搜索 |
| DELETE | `/api/kb/documents/{doc_id}` | 删除文档并下索引 |
| POST | `/api/kb/rebuild` | 全量重建向量索引(幂等,upsert 不先清库) |
| GET | `/api/settings/intent` | 读取意图识别开关状态 |
| POST | `/api/settings/intent` | 运行时切换意图识别开关(立即生效) |

> 错误表达:后端不套 `{code,msg,data}` 外壳,成功返回数据对象/数组,失败返回 HTTP 状态码 + `{"detail":"中文描述"}`。前端经 `src/lib/api.js` 统一封装、统一把非 2xx 抛成 `Error(detail)`。

完整契约(含数据模型、上传任务时序、前端请求封装映射)见 [docs/API.md](docs/API.md)。

## 项目结构

```
RAG/
├── README.md
├── pyproject.toml / uv.lock / requirments.txt   # 依赖（requirments.txt 在根目录）
├── config.ini          # 根配置（gitignore，不常用；应用实际加载的是 integrated_qa_system/config.ini）
├── deploy.sh           # 手动一键部署脚本
├── static/             # 前端构建产物（由 FastAPI 托管）
├── docs/               # 文档
└── integrated_qa_system/
    ├── app.py                  # FastAPI 入口（REST + WebSocket + 静态托管）
    ├── new_main.py             # IntegratedQASystem（会话/历史/图编排）
    ├── config.ini              # 应用实际加载的系统配置（gitignore，不入库，含密钥）
    ├── base/                   # Config 加载 + logger
    ├── mysql_qa/
    │   ├── db/                 # MySQL 会话历史 + Redis 缓存
    │   ├── retrieval/          # BM25（rank_bm25）快速命中
    │   └── data/               # BM25 问题语料
    ├── rag_qa/
    │   ├── core/
    │   │   ├── graph.py            # LangGraph 编排层（classify/analyze/bm25/retrieve/generate）
    │   │   ├── rag_system.py       # 检索合并 + LLM 生成
    │   │   ├── vector_store.py     # Milvus 混合检索 + BGE-Reranker
    │   │   ├── query_classifier.py # BERT 查询分类器
    │   │   ├── strategy_selector.py# 问题解析(analyze) + 检索策略
    │   │   ├── prompts.py          # Prompt 模板
    │   │   └── document_processor.py # 文档切分
    │   ├── edu_document_loaders/   # 各类型文档加载器
    │   ├── edu_text_spliter/       # 文本切分器
    │   ├── bert_query_classifier/  # BERT 分类模型权重/脚本
    │   ├── bge-m3 / bge-reranker-large/  # 本地嵌入与重排模型
    │   └── data/                   # {subject}_data/ 文档源文件
    ├── frontend/               # React 源码（Vite）
    ├── static/                 # 前端构建产物（FastAPI 托管）
    └── logs/                   # 运行日志
```

## 检索策略

LLM 在 `analyze` 阶段为每次查询自动选择最适合的向量检索增强策略:

- **直接检索**:查询意图明确,直接用(规范)查询向量检索。
- **假设问题检索(HyDE)**:LLM 先生成假设答案,再用假设答案检索。
- **子查询检索**:复杂查询拆分多个子查询,分别检索后合并。
- **回溯问题检索**:把复杂 / 口语化问题简化为基础问题后再检索。

## 常见问题

- **MySQL 连接失败 `WinError 10061`**:MySQL 服务未运行。启动对应服务(`net start MySQL80`,需管理员),或确认免安装版 mysqld 已在运行;随后确认 `config.ini` 里的 `database` 已存在。
- **Milvus 连接失败**:确认 `docker compose` 已拉起 Milvus + etcd,且 `database_name` / `collection_name` 已在 `config.ini` 指定并预建。
- **回答不命中**:调低 `retrieval_k` / 提高 `bm25_threshold`,或检查文档是否已切块入库(知识库页面上传或 `rag_main.py --data-processing`)。

## 文档

- [docs/API.md](docs/API.md) — 接口契约(前后端对齐基准)
- [docs/DEV.md](docs/DEV.md) — 开发文档(技术栈、目录、启动、本地基础设施)
- [docs/FRONTEND.md](docs/FRONTEND.md) — 前端开发说明(面向从零开发的对接者)
- `docs/QUICKSTART.md` — 本地学习资料(不入版本库)

## License

MIT