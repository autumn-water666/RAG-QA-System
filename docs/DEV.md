# EduRAG 开发文档

教育领域 RAG 问答系统。技术栈、目录、启动与协作约定。

## 技术栈

- **后端**：Python + FastAPI；LangGraph（0.6）编排；MySQL(会话) + Redis + Milvus(BGE-M3) + BGE-Reranker；LLM 走 Mimo/DashScope 兼容 OpenAI 接口。
- **前端**：Vite + React 18 + react-router-dom（HashRouter）+ 手写 CSS（CSS 变量双主题）。不用 Tailwind / Next.js。
- **构建**：前端 `npm run build` 产物输出到 `static/`，由 FastAPI 根挂载托管，同域部署。

## 目录

```
integrated_qa_system/
  app.py             FastAPI 入口：REST + WebSocket + 静态托管
  new_main.py        IntegratedQASystem：会话/历史/Mysql/图编排
  base/              配置 Config + 日志 logger
  mysql_qa/          MySQL 会话历史 + Redis + BM25（rank_bm25）
  rag_qa/
    core/
      graph.py       LangGraph 编排层（classify/bm25/retrieve/generate）
      rag_system.py  检索合并 + LLM 生成
      vector_store.py BGE-M3 混合检索 + Reranker + Milvus
      ...
  frontend/
    src/
      lib/api.js     前端请求层（文档见 docs/API.md §7）
      pages/         工作台 / 知识库 / 文档详情 / 设置
      components/    气泡 / 会话列表 / 输入区 / 导航 / 主题开关
      theme.js       双主题 hook
      App.css        设计 tokens（CSS 变量）+ 组件样式
docs/
  API.md             接口契约（前后端对齐基准）
  DEV.md             本文档
```

## 启动

```bash
# 后端
cd integrated_qa_system
uvicorn app:app --host 0.0.0.0 --port 8000

# 前端（改样式后）
cd frontend
npm run build        # 产物 → static/，刷新浏览器即可
```

前端开发用 `npm run dev`（5173，代理 `/api` 与 ws `/api/stream` 到 8000）。

## 关键流程

```
UI 提问 ──ws──▶ /api/stream
  ▶ LangGraph: classify ──通用知识──▶ generate
                          └大专业咨询──▶ bm25 ──命中──▶ 直答
                                         │ 需RAG
                                         └▶ retrieve(混合召回)──▶ generate
  ▶ end 帧(规划带 sources 引用溯源) ──▶ 前端渲染
```

- 会话写 MySQL `conversations` 表，按 `session_id` 隔离。
- 检索返回带 `metadata` 的 Document（`source/parent_id/parent_content/timestamp`），引用溯源从此映射。

## 约定

- 接口变更先改 `docs/API.md`（见 §0 copy 约定）。
- 提交信息写详细，分点列出改动（见记忆规范）。
- 后端不套 `{code,msg,data}` 外壳，用原生 REST + `{"detail":...}` 错误。

## 本地基础设施（Docker）

不在仓库内，由 `E:\develop\docker_data\docker-compose.yml` 维护（docker_data 项目），连接凭据见 `config.ini`：

| 服务 | 镜像 | 端口 | 认证 |
|---|---|---|---|
| Milvus | `zilliztech/milvus:v2.6.18`（阿里镜像源）| 19530(gRPC) / 9091(管理，无 WebUI) | **未开鉴权**，客户端不传 user/password |
| etcd | `quay.io/coreos/etcd:v3.5.5` | 2379 | — |
| MySQL | `mysql:8.0` | 3306 | root / 123456 |
| Redis | `teable/redis:7.2.4` | 6379 | 密码 1234 |

- Milvus 存储为 **local**（`milvus_data` 命名卷），无 MinIO；元数据在 etcd（容器层，未挂卷）。
- Milvus 曾从 2.5.4 升到 2.6.18（相邻小升级数据保留）；升级前备份在 `E:\develop\docker_data\backup\milvus_data_*.tar.gz`。
- Attu 图形客户端需 v2.x（连 2.4/2.5）或 v3.0（连 2.6+/3.x），认证选「无」。