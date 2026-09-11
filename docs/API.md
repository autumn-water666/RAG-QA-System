# EduRAG 接口契约文档

前后端共同对齐的地基。**「已有」**= 后端已实现；**「规划」**= 后端未实现，前端已备好占位，按本文契约开发。

---

## 0. 总体约定

- **传输**：JSON（UTF-8）。生产同域部署，FastAPI 托管前端静态资源，base path 为空。
- **错误表达**：后端**不套** `{code,msg,data}` 外壳，用原生 REST——
  - 成功：`2xx`，请求体直接返回数据对象/数组。
  - 失败：HTTP 错误码 + `{"detail": "<中文描述>"}`（FastAPI 默认）。
  - 前端判断成败：看 `response.ok`；取错误信息读 `detail`。
- **命名**：后端字段 `snake_case`，前端照用，不做驼峰转换。
- **鉴权**：当前无登录，不做身份校验；**会话隔离**靠 `session_id` 主键。
- **跨域**：后端已开 CORS（`*`），但同域部署基本用不到。

### copy 约定

```diff
+ 新增/修改接口：先改本文档（含字段表），再动代码。
+ 前端每条请求都经 src/lib/api.js 封装，不散落裸 fetch。
```

---

## 1. 部署与运行

```bash
# 后端（项目根 integrated_qa_system/）
uvicorn app:app --host 0.0.0.0 --port 8000

# 前端构建（frontend/）
npm install
npm run build     # 产物输出到 ../static，由 FastAPI 根挂载托管

# 前端开发联调（可选，vite dev 代理 /api 与 ws 到 8000）
npm run dev
```

前端用 **HashRouter**：URL 形如 `#/` 、`#/kb`、`#/kb/:id`、`#/settings`，刷新不依赖服务器路由。

---

## 2. 通用错误

| 状态码 | 含义 | body |
|---|---|---|
| 400 | 参数错误 / 非法学科过滤 | `{"detail":"..."}` |
| 404 | 资源不存在（如 session/doc） | `{"detail":"..."}` |
| 500 | 服务端异常 | `{"detail":"..."}` |
| 502/504 | 上游 LLM/向量库异常 | `{"detail":"..."}` |

前端 `src/lib/api.js` 统一把非 2xx 抛成 `Error(detail)`。

---

## 3. 接口目录汇总

| 方法 | 路径 | 状态 | 用途 |
|---|---|---|---|
| GET | `/health` | 已有 | 健康检查 |
| GET | `/api/sources` | 已有 | 有效学科列表 |
| POST | `/api/create_session` | 已有 | 创建会话 |
| GET | `/api/sessions` | 已有 | 会话列表（隔离切换） |
| GET | `/api/history/{session_id}` | 已有 | 查询会话历史 |
| DELETE | `/api/history/{session_id}` | 已有 | 清除会话历史 |
| POST | `/api/query` | 已有(兼容) | 非流式查询（前端不再用） |
| WS | `/api/stream` | 已有 | 流式问答（WebSocket） |
| WS | `end`.sources 透出 | 已有 | 引用溯源 |
| GET | `/api/kb/documents` | 已有 | 知识库文档列表 |
| GET | `/api/kb/documents/{doc_id}` | 已有 | 文档详情（全文+切块） |
| POST | `/api/kb/documents` | 已有 | 上传文档，增量索引 |
| DELETE | `/api/kb/documents/{doc_id}` | 已有 | 删除文档并下索引 |
| GET | `/api/kb/search` | 已有 | 库内全文/语义搜索 |
| POST | `/api/kb/rebuild` | 已有 | 重建知识库索引 |
| GET | `/api/settings/intent` | 已有 | 读取意图识别开关 |
| POST | `/api/settings/intent` | 已有 | 运行时切换意图识别开关 |
| POST | `/api/sessions/{sid}/feedback` | 规划 | 答案反馈 👍/👎 |

---

## 4. 数据模型

```ts
// 会话（列表项）
type Session = {
  session_id: string
  preview: string          // 最后一条问题，做列表预览
  count: number            // 轮数
  last_time: string | null // ISO8601
}

// 一条历史问答
type HistoryItem = {
  question: string
  answer: string
  sources?: Source[]       // 规划：该条答案的引用来源
}

// 引用来源（规划，引用溯源）
type Source = {
  index: number            // 1 起始，对应答案正文 [N] 角标
  title: string            // 文档标题
  subject: string          // 所属学科
  snippet: string          // 命中片段摘要
  url: string              // 前端文档详情路由，形如 #/kb/{parent_id}
}

// 文档列表项（规划）
type DocSummary = {
  id: string               // 文档唯一标识（父文档 id）
  title: string
  subject: string
  updated_at: string
  chunk_count: number
}

// 文档详情（规划）
type DocDetail = DocSummary & {
  content: string          // 全文
  chunks: Array<{ id: string; text: string; score?: number }>
}
```

---

## 5. 接口详述

### 5.1 GET `/health`
**返回**
```json
{ "status": "healthy" }
```

### 5.2 GET `/api/sources`
**返回**
```json
{ "sources": ["ai", "java", "test", "ops", "bigdata"] }
```
来源：`Config().VALID_SOURCES`（config.ini 中的 `valid_sources`）。

### 5.3 POST `/api/create_session`
无请求体。
**返回**
```json
{ "session_id": "01234567-...." }
```
> 后端总是生成新 uuid。前端把 `session_id` 存 `localStorage`，刷新复用。

### 5.4 GET `/api/sessions`
**返回**
```json
{ "sessions": [ { "session_id": "...", "preview": "...", "count": 3, "last_time": "2026-09-08T15:00:00" } ] }
```
按 `last_time` 倒序，仅包含已有对话记录的会话。

### 5.5 GET `/api/history/{session_id}`
**返回**（最近 5 轮，正序）
```json
{ "session_id": "...", "history": [ { "question": "...", "answer": "..." } ] }
```

### 5.6 DELETE `/api/history/{session_id}`
**返回**
```json
{ "status": "success", "message": "历史记录已清除" }
```

### 5.7 POST `/api/query`（兼容保留，前端不再调用）
```json
// 请求
{ "query": "string", "source_filter": "string|null", "session_id": "string|null" }
// 返回
{ "answer": "...", "is_streaming": false, "session_id": "...", "processing_time": 0.5 }
```

### 5.8 WS `/api/stream`（核心）
WebSocket 单通道。客户端一次连接一答一问。

**客户端 → 服务端**（收到 `start` 后与服务端建流）
```json
{ "query": "...", "source_filter": "string|null", "session_id": "string|null" }
```
> `session_id` 传 `null` = 独立查询（不带上文、不写入本会话历史）——前端「续文追问」关闭时用。

**服务端 → 客户端**（四类帧）
```jsonc
// 1) 开始
{ "type": "start", "session_id": "..." }

// 2) 流式 token（多次）
{ "type": "token", "token": "...", "session_id": "..." }

// 3) 结束
{ "type": "end", "session_id": "...", "is_complete": true, "processing_time": 2.3,
  "sources": [ /* 规划：引用溯源，Source[]，见 4 */ ] }

// 4) 错误
{ "type": "error", "error": "中文描述" }
```

**流程**：`start` → `token`×N → `end`。前端收到 `end` 关闭连接；收到 `error` 展示后关闭。问候语/BM25 快答也会走 token 单次 + end。

**引用溯源**：服务端在 `end` 帧携带 `sources`。生成方式：`retrieve` 节点持有的 `state["context_docs"]`（带 `metadata` 的父文档列表）经 `graph._build_sources()` 映射为 `Source[]`，随 `end` 帧透出——
```
index    ≤ 检索排序
title    文档标题（后端实现时从 document_processor 元数据取，缺省回退 "文档片段N"）
subject  doc.metadata["source"]
snippet  doc.page_content 前 ~80 字
url      `#/kb/${doc.metadata["parent_id"]}`
```
前端收到 `end.sources` 即挂在当前助手消息上，渲染 `[N]` 角标 + 「参考来源」卡片。

### 5.9 GET `/api/settings/intent`
读取意图识别开关当前状态。

**响应** `200`
```json
{ "use_intent_classify": true }
```
> 对应 App 层 `IntegratedQASystem.get_intent_classify()` → 图模块 `conf.USE_INTENT_CLASSIFY`。

### 5.10 POST `/api/settings/intent`
运行时切换意图识别开关，立即生效（改图模块配置并重编译 LangGraph 编排图）。

**请求体**
```json
{ "enabled": false }
```

**响应** `200`，返回切换后状态
```json
{ "use_intent_classify": false }
```

**错误** `400`：`enabled` 非布尔值。

---

## 6. 待开发知识库接口（规划，URL 占位）

### 6.1 GET `/api/kb/documents?subject=ai&q=`
- `subject` 过滤学科（非法值 → 400）；`q` 可选库内关键词（正文 LIKE）过滤。
- **返回** `{ "documents": DocSummary[] }`。按 `doc_id` 聚合 Milvus 子块生成，`chunk_count` 为块数。

### 6.2 GET `/api/kb/documents/{doc_id}`
- **返回** `DocDetail`（含全文 + 有序切块），不存在返回 404。

### 6.3 POST `/api/kb/documents`（批量上传，multipart/form-data，异步）
- **请求体**：文件字段 `files`（可多个，同名重复 append），必填表单字段 `subject`（非法值 → 400）。
- **行为**：文件先全部校验并落盘到 `rag_qa/data/.staging/{job_id}/`，**立即返回 job_id**；切块 → 向量化 → 写入 Milvus 在后台线程执行，**不阻塞事件循环**（其它 WebSocket 问答不受影响）。完成后把文件 move 到 `rag_qa/data/{subject}_data/`（同名覆盖），`doc_id` = 落盘绝对路径 md5。单个文件失败只删该文件及其索引，不影响同批次其它文件。
- **返回** `{ "job_id": "...", "total": 5 }`
- **进度查询**：`GET /api/kb/uploads/{job_id}` → `{ total, done, failed, finished, items: [{file,status,message,title,chunk_count}] }`，`status` ∈ `pending/processing/done/error`，`finished=true` 表示处理完毕。任务存内存，重启后失效（重新提交即可）。

### 6.4 DELETE `/api/kb/documents/{doc_id}`
- **行为**：下索引 + 删除磁盘源文件（源文件路径从 Milvus 块元数据取）。
- **返回** `{ "status": "success", "deleted_chunks": 1 }`；不存在时 `deleted_chunks` 为 0。

### 6.5 GET `/api/kb/search?q=&subject=`
- `q` 必填；`subject` 可选（非法值 → 400）。
- **返回** `{ "results": [ { "doc_id": "...", "title": "...", "snippet": "...", "score": 0.85 } ] }`。
  v1 用正文 LIKE 关键词匹配按文档聚合，`score` 暂为 `null`；后续可切向量检索带距离分。

### 6.6 POST `/api/kb/rebuild`
- 全量重建：遍历 `rag_qa/data/*_data` 目录重新切块并 `upsert`（块主键 = 文本哈希，幂等，不先清库，避免重建中断清空索引）。
- **返回** `{ "status": "success", "subjects": { "ai": 12 }, "total_chunks": 12 }`。

---

## 7. 前端请求封装映射（src/lib/api.js）

| 后端 | 前端函数 |
|---|---|
| `GET /health` | `api.health()` |
| `GET /api/sources` | `api.getSources()` → `Source[]` |
| `POST /api/create_session` | `api.createSession()` → `{ session_id }` |
| `GET /api/sessions` | `api.getSessions()` → `Session[]` |
| `GET /api/history/{id}` | `api.getHistory(sid)` → `HistoryItem[]` |
| `GET /api/kb/documents` | `api.getDocuments(subject, q)` → `DocSummary[]` |
| `GET /api/kb/documents/{id}` | `api.getDocument(docId)` → `DocDetail` |
| `GET /api/kb/search` | `api.kbSearch(q, subject)` → `Result[]` |
| `DELETE /api/history/{id}` | `api.clearHistory(sid)` |
| `DELETE /api/kb/documents/{id}` | `api.deleteDocument(docId)` |
| `POST /api/kb/rebuild` | `api.rebuildIndex()` |
| `GET /api/settings/intent` | `api.getIntentClassify()` → `bool` |
| `POST /api/settings/intent` | `api.setIntentClassify(enabled)` → `bool` |
| `WS /api/stream` | `api.wsStreamUrl()` → 连接串 |

---

## 8. Roadmap（后端补接口顺序）

1. ✅ `end.sources` 透出（引用溯源点亮前端「参考来源」，已上线）
2. ✅ `GET /api/kb/documents` + `GET /api/kb/documents/{id}`（知识库浏览 + 文档详情，已上线）+ `GET /api/kb/search`（库内搜索）
3. ✅ `POST /api/kb/documents`（上传/增量索引）+ `DELETE /api/kb/documents/{id}`（删除）+ `POST /api/kb/rebuild`（重建，已上线）
4. ✅ `GET /api/kb/search`（库内搜索）
5. ✅ `GET/POST /api/settings/intent`（前端意图识别开关，运行时重编译，已上线）
6. `POST /api/.../feedback`（答案 👍/👎 反馈）