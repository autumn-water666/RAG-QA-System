// 前端请求层：与 docs/API.md §7 一一对应。
// 后端用原生 REST（成功 2xx 直接返回数据，失败抛 Error(detail)），这里统一封装，
// 页面组件不再散落裸 fetch。
const API = ''

async function jfetch(path, options = {}) {
  const r = await fetch(`${API}${path}`, options)
  if (!r.ok) {
    let msg = `请求失败 ${r.status}`
    try {
      const d = await r.json()
      if (d && d.detail) msg = d.detail
    } catch {
      /* 非 JSON 响应，保留默认错误信息 */
    }
    throw new Error(msg)
  }
  return r.json()
}

function wsBase() {
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
}

export const api = {
  // ---- 会话 ----
  createSession: () => jfetch('/api/create_session', { method: 'POST' }), // -> { session_id }
  getSessions: async () => (await jfetch('/api/sessions')).sessions, // -> Session[]
  getHistory: async (sid) => (await jfetch(`/api/history/${sid}`)).history, // -> HistoryItem[]
  clearHistory: (sid) => jfetch(`/api/history/${sid}`, { method: 'DELETE' }),

  // ---- 来源 ----
  getSources: async () => (await jfetch('/api/sources')).sources, // -> string[]

  // ---- 知识库 ----
  getDocuments: async (subject, q = '') => {
    const params = new URLSearchParams()
    if (subject) params.set('subject', subject)
    if (q) params.set('q', q)
    return (await jfetch(`/api/kb/documents?${params}`)).documents // -> DocSummary[]
  },
  getDocument: (docId) => jfetch(`/api/kb/documents/${docId}`), // -> DocDetail
  kbSearch: async (q, subject) => {
    const params = new URLSearchParams({ q })
    if (subject) params.set('subject', subject)
    return (await jfetch(`/api/kb/search?${params}`)).results // -> Result[]
  },

  // ---- 健康 ----
  health: async () => (await jfetch('/health')).status, // -> 'healthy'

  // ---- 流式 ----
  wsStreamUrl: () => `${wsBase()}/api/stream`,
}