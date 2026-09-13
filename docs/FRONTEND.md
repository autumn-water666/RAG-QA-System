# 前端开发说明文档

> 本文件面向**从未接触过本项目**的前端开发者。前后端完全分离,前端框架/技术栈由你自选,
> 文档只规定「产品要做什么」和「后端给什么契约」,不含任何现有前端实现细节。
> 依照本文件,你可以从零做出一个功能完整的前端,替换现有的 `frontend/`。

---

## 0. 一句话理解这个产品

一个**通用智能问答系统**(不限业务领域),包含三个核心能力:

1. **对话问答** —— 用户在 Web 界面提问,后端把问题检索知识库后用大模型流式生成答案,可多轮追问、可查看「参考来源」。
2. **知识库管理** —— 用户可以浏览、搜索、删除已入库文档,并按**主题**(英文/中文短词)批量上传新文档,"主题"由用户自由创建,系统没有固定分类。
3. **意图识别开关** —— 一个运行时开关,控制后端是否对问题做「通用闲聊 / 专业咨询」意图识别。

产品由 4 个页面组成(见 §2),顶部导航切换。

---

## 1. 全局约定(前端必须遵守)

| 约定 | 说明 |
|---|---|
| 传输格式 | JSON(UTF-8)。生产同域部署,`basePath` 为空。 |
| 错误表达 | 后端**不套任何外壳**(没有 `{code,msg,data}`)。<br/>— 成功:`2xx`,响应体就是数据<br/>— 失败:HTTP 错误码 + `{"detail": "<中文描述>"}`<br/>前端判断成败只看 `response.ok`,报错信息固定读 `detail`。 |
| 字段命名 | 后端一律 `snake_case`,前端照用,**不转驼峰**。 |
| 鉴权 | **无登录**、无身份校验。会话隔离靠一个 `session_id` 主键。 |
| 跨域 | 后端已开 CORS(`*`),但同域部署基本用不到。 |
| 路由 | 前端用 **hash 路由**(URL 形如 `#/`、`#/kb/:id`),刷新不依赖服务器。 |

### 会用到的一组 localStorage 键
由前端自行管理,键名前缀 `rag_`(可自定义但保持一致即可):

| 键 | 存什么 | 何时用 |
|---|---|---|
| `rag_session` | 当前 `session_id` | 刷新页面后恢复同一会话 |
| `rag_theme` | 主题偏好:`'auto'\|'light'\|'dark'` | 页面启动时读取 |

---

## 2. 产品功能规格(要做什么,逐页)

### 2.1 整体布局
顶部导航:Logo/标题 + 三个入口「对话」「知识库」「设置」,加一个**主题切换**按钮(亮 / 暗 / 跟随系统 三态循环)。全局支持深色模式。

### 2.2 对话页 `#/`
页面分左右两栏(移动端可上下堆叠):

- **侧栏(会话)**:
  - 会话列表(每项显示最后一句问题预览、轮数、时间),按时间倒序。
  - 「新建会话」按钮;「清除当前会话历史」操作。
  - **主题过滤**下拉/多选:可选「全部」或某个主题 —— 选中后,提问只在选定主题范围内检索。选项来自 `sources` 接口(见 §4.2)。
  - 「续文追问」开关:开着=提问带上连续上下文(发送 `session_id`);关掉=每次独立提问(发送 `session_id: null`)。
- **主区(聊天)**:
  - 消息列表:用户问题 / 助手回答,气泡式;助手回答支持**流式打字机**效果(逐 token 显示)。
  - 输入框 + 发送;流式进行中可「停止」。
  - 助手回答带**引用来源**时,在消息下方渲染「参考来源」卡片(§5.2,序号 `[N]` 角标与正文对应,可点击跳转到对应文档详情页)。
  - 底部自动滚动到最新消息。

**无历史时的兜底**:页面加载时若无有效会话,自动 `create_session` 并显示一条欢迎语。

### 2.3 知识库页 `#/kb`
- 顶部一行**主题标签**(来自 `sources`),点击切换当前浏览主题;当前主题高亮。
- 右上:
  - 一个**库内搜索框**(按关键词过滤当前主题内文档,输入即查);
  - 一个**上传主题输入框**(带可选下拉建议,值默认取当前浏览主题,也可手填**新主题**——填新就能直接创建分类);
  - **「上传文档」按钮** —— 点击弹出多选文件,支持 `.txt .md .pdf .doc .docx .ppt .pptx .rtf .epub .csv .xls .xlsx`。
- 主区:该主题下的**文档卡片列表**(标题、主题、切块数、更新时间),点击跳转文档详情。
- 空状态:当前主题无文档时给出引导文案。
- **上传交互(重点,异步)**:选中文件后**立即提交**,拿到 `job_id` 后**轮询进度接口**,界面上显示「正在处理 n/total」;全部完成(或部分失败)后自动刷新文档列表并提示成功/失败数量,并自动把新主题上浮到主题栏。**不要做成「点一下等同步返回」**。

### 2.4 文档详情页 `#/kb/:docId`
展示一篇已入库文档:标题、主题、全文、以及**有序的切块列表**(每块可显示命中分)。数据来自 `GET /api/kb/documents/{doc_id}`。

### 2.5 设置页 `#/settings`
一个开关:「意图识别」—— 读取/切换后端的运行时意图识别开关(§4.8)。变化即时生效并回显。

---

## 3. 数据模型(类型定义,字段后端已定死,别改)

```ts
// 3.1 会话列表项
type Session = {
  session_id: string
  preview: string            // 最后一句问题,做列表预览
  count: number              // 轮数(问答对数)
  last_time: string | null   // ISO8601
}

// 3.2 一条历史问答
type HistoryItem = {
  question: string
  answer: string
  sources?: Source[]         // 该条答案的引用来源(可能缺失/为空数组)
}

// 3.3 引用来源(答案溯源)
type Source = {
  index: number              // 从 1 开始,对应答案正文的 [N] 角标
  title: string              // 文档标题
  subject: string            // 所属主题
  snippet: string            // 命中片段摘要
  url: string                // 前端文档详情路由,形如 #/kb/{doc_id}
}

// 3.4 文档列表项
type DocSummary = {
  id: string                 // 文档唯一标识(父文档 id)
  title: string
  subject: string
  updated_at: string         // ISO8601
  chunk_count: number        // 切块数
}

// 3.5 文档详情
type DocDetail = DocSummary & {
  content: string                                            // 全文
  chunks: Array<{ id: string; text: string; score?: number }> // 有序切块
}

// 3.6 知识库搜索命中
type KbSearchResult = {
  doc_id: string
  title: string
  snippet: string
  score: number | null       // 当前为 LIKE 匹配,score 为 null;后续可能给向量分
}

// 3.7 批量上传任务状态
type UploadStatus = {
  id: string
  subject: string
  total: number              // 总共文件数
  done: number               // 已成功
  failed: number             // 已失败
  finished: boolean          // true 表示全部处理完毕(此时才该结束轮询)
  items: Array<{
    file: string             // 文件名
    status: 'pending' | 'processing' | 'done' | 'error'
    message: string          // error 时的原因;其余为空
    title: string            // 成功后的文档标题
    chunk_count: number      // 成功后的切块数
  }>
}
```

---

## 4. 接口契约(全部)

> `WebSocket` 由于无法用普通 fetch 封装,单独在 §5 说明。

### 4.0 通用错误(对所有接口适用)
| 状态码 | 含义 | body |
|---|---|---|
| 400 | 参数错误 / 非法主题过滤值 | `{"detail":"..."}` |
| 404 | 资源不存在(会话/文档/上传任务) | `{"detail":"..."}` |
| 500 | 服务端异常 | `{"detail":"..."}` |
| 502/504 | 上游大模型/向量库异常 | `{"detail":"..."}` |

### 4.1 接口总览
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/sources` | 主题列表 |
| POST | `/api/create_session` | 创建会话 |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/history/{session_id}` | 会话历史 |
| DELETE | `/api/history/{session_id}` | 清除会话历史 |
| WS | `/api/stream` | 流式问答(见 §5) |
| GET | `/api/kb/documents` | 文档列表(按主题/关键词) |
| GET | `/api/kb/documents/{doc_id}` | 文档详情 |
| POST | `/api/kb/documents` | 批量上传(异步,§4.7) |
| GET | `/api/kb/uploads/{job_id}` | 上传任务进度 |
| DELETE | `/api/kb/documents/{doc_id}` | 删除文档 |
| GET | `/api/kb/search` | 库内搜索 |
| POST | `/api/kb/rebuild` | 全量重建向量索引 |
| GET | `/api/settings/intent` | 读取意图识别开关 |
| POST | `/api/settings/intent` | 切换意图识别开关 |

### 4.2 GET `/api/sources`
**返回**
```json
{ "sources": ["ai", "java"] }
```
> 注意:**主题是数据驱动的**,没有固定默认分类 —— 它合并了磁盘实际目录 + 向量库中已有数据,随用户上传/新建而增长。前端拿到的就是一个字符串数组,别写死任何默认值。

### 4.3 会话三件套
```jsonc
// POST /api/create_session  无请求体
{ "session_id": "01234567-8b40-42eb-xxxx-xxxxxxxxxxxx" }   // 总是新 uuid

// GET /api/sessions  按 last_time 倒序,仅含已有对话的记录
{ "sessions": [
    { "session_id": "...", "preview": "最近问的问题", "count": 3, "last_time": "2026-09-11T10:00:00" }
] }

// GET /api/history/{session_id}  最近 5 轮,正序
{ "session_id": "...", "history": [
    { "question": "你好", "answer": "你好,有什么可以帮你?" }
] }

// DELETE /api/history/{session_id}
{ "status": "success", "message": "历史记录已清除" }
```

### 4.4 GET `/api/kb/documents`
查询参数:`subject`(可选,按主题过滤,非法值 → 400)、`q`(可选,库内关键词过滤)。
**返回**
```json
{ "documents": [
    { "id": "...", "title": "文档名", "subject": "ai", "updated_at": "2026-09-11T10:00:00", "chunk_count": 12 }
] }
```

### 4.5 GET `/api/kb/documents/{doc_id}` / DELETE `/api/kb/documents/{doc_id}`
- GET:**返回** `DocDetail`(§3.5);不存在 → 404。
- DELETE:**返回** `{ "status": "success", "deleted_chunks": 12 }`;不存在时 `deleted_chunks` 为 0。

### 4.6 GET `/api/kb/search`
查询参数:`q`(必填)、`subject`(可选)。
**返回**
```json
{ "results": [
    { "doc_id": "...", "title": "...", "snippet": "...", "score": null }
] }
```

### 4.7 POST `/api/kb/documents`(批量上传,multipart/form-data,**异步**)
> 上传富文本步骤必须拆成「提交 → 轮询」两段,不能一边等一边堵死 UI。

- **请求体**:字段 `files`(可多个文件,用同一个字段名重复 append)+ 字段 `subject`(**必填**,主题,填新主题即创建新分类)。
- **行为**:后端先同步校验文件名/扩展名(非法 → 400),随后**立即返回 `job_id`**,真正的切块→向量化→入库在**后台线程**异步执行,不阻塞其它请求。单个文件出错只回滚该文件,不影响同批其它文件。
- **返回**
  ```json
  { "job_id": "一串 hex", "total": 5 }
  ```
- **进度轮询**:`GET /api/kb/uploads/{job_id}` → `UploadStatus`(见 §3.7)。`finished === true` 时结束轮询并刷新列表。
  > 注意:任务状态存在**后端内存**,后端重启即失效(文件可能已入库,重新提交即可)。前端轮询到 404 时视为任务丢失,停止轮询即可。

### 4.8 意图识别开关
```jsonc
// GET /api/settings/intent
{ "use_intent_classify": true }

// POST /api/settings/intent  请求体
{ "enabled": false }            // enabled 非布尔 → 400
// 返回切换后的状态
{ "use_intent_classify": false }
```

### 4.9 POST `/api/kb/rebuild`
无请求体,全量重建,幂等。
**返回**
```json
{ "status": "success", "subjects": { "ai": 12 }, "total_chunks": 12 }
```

### 4.10 `POST /api/query`(兼容保留,前端**不要用**)
非流式旧接口,已由 WebSocket 取代。

---

## 5. WebSocket 流式问答 `/api/stream`(核心协议)

一次连接 = 一问一答。单通道,发一条消息,陆续收到若干帧,收到 `end` 或 `error` 后关闭。

### 5.1 客户端 → 服务端(连接建立后发送)
```json
{ "query": "问题", "source_filter": "ai", "session_id": "会话id或null" }
```
- `source_filter`:为 `null`/空 = 全库检索;填主题值 = 只在该主题内检索。
- `session_id`:传 `null` = **独立查询**(不带上文、不写入会话历史)——即前端「续文追问」关闭时的行为;传真实 id = 多轮追问。

### 5.2 服务端 → 客户端(四类帧)
```jsonc
// (1) 开始 —— 告诉前端这次问答归属的会话
{ "type": "start", "session_id": "..." }

// (2) 流式 token —— 会出现多次,内容按顺序拼起来就是完整回答
{ "type": "token", "token": "你好，", "session_id": "..." }

// (3) 结束 —— 携带引用溯源
{ "type": "end", "session_id": "...",
  "is_complete": true, "processing_time": 2.3,
  "sources": [
    { "index": 1, "title": "某文档", "subject": "ai",
      "snippet": "命中片段前80字…", "url": "#/kb/{doc_id}" }
  ] }

// (4) 错误 —— 展示后即可关闭
{ "type": "error", "error": "中文描述" }
```

### 5.3 前端必须处理的细节
- **顺序**:`start` → `token`×N → `end`。前端收到 `start` 后进入流式状态;把 `token` 累积拼接到当前助手消息。
- **何时关连接**:收到 `end` 或 `error` 即 `ws.close()`;用户点「停止」时也主动关闭。
- **兜底**:`end` 帧可无 `sources`(非检索类回答)或为 `null`,前端要容错;`is_complete` 为完成标记,基本恒为 true。
- **渲染引用来源**:`sources[].index` 对应该条回答正文里的 `[N]` 角标。渲染成可点卡片,`url` 是前端 hash 路由(`#/kb/{doc_id}`),点击跳文档详情。
- **流式渲染性能**:tokens 高频到达,建议合并为**节流渲染**(每 ~40ms 刷新一次 DOM),否则长回答会卡顿。

---

## 6. 主题与状态

- 完整主题状态来自 `GET /api/sources`,但**上传后**系统可能新增主题 —— 所以知识库页在**每次上传任务完成后重新拉一次** `sources`。
- 会话列表每次问答结束后也会增加/更新 —— 建议在 WebSocket `close` 时刷新一次会话列表。

---

## 7. 验收清单(完成后逐项自查)

- [ ] 四个页面可正常跳转;刷新任一 hash 路由不白屏。
- [ ] 输入问题 → 逐 token 流式显示 → 结束时若带来源则渲染「参考来源」卡片,点击可跳详情。
- [ ] 新建/切换/清除会话;「续文追问」开关:开=能接上文,关=独立回答。
- [ ] 「主题过滤」能限定检索范围;选项来自 `sources` 且不为写死值。
- [ ] 知识库:按主题浏览、关键词搜索、查看文档详情与切块。
- [ ] 批量上传:多选文件 → 提交立即返回 → 轮询显示进度 → 完成后自动刷新列表并提示成功/失败数。
- [ ] 上传页能直接填**新主题**并成功创建该分类;上传失败的文件给出可读错误文案,且不污染列表。
- [ ] 设置页能读取/切换「意图识别」开关,刷新后仍为最新值。
- [ ] 深色模式正常;英文环境不出现乱码/硬编码错位。

---

## 8. 对接环境参考
- 开发联调:后端 `uvicorn app:app --host 0.0.0.0 --port 8000`;前端 `npm run dev` 时把 `/api` 和 `/api/stream`(ws)代理到 `:8000` 即可。
- 生产:前端 `npm run build` 产物放到后端同域由 FastAPI 托管(同域,basePath 空),无需处理 CORS。