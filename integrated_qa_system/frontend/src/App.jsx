import { useEffect, useRef, useState } from 'react'
import { Marked } from 'marked'
import DOMPurify from 'dompurify'

// 前后端同域部署（FastAPI 托管前端），API 均为相对路径。
// 全部会话走 WebSocket 单通道：问候 / BM25 快答 / RAG 流式由后端统一返回 token，
// 前端不再先打 /api/query 探路，避免一次提问两次请求（旧实现的开销）。
const API = ''
const WS_BASE =
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/stream`

const md = new Marked({ breaks: true, gfm: true })

function renderMarkdown(text) {
  // marked 产物先进 DOMPurify，防止检索回来的文档带 HTML 被注入（XSS）
  return { __html: DOMPurify.sanitize(md.parse(text || '')) }
}

const WELCOME = '您好！我是智能问答助手，有什么我可以帮您的吗？'

export default function App() {
  const [sessionId, setSessionId] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sources, setSources] = useState([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

  const socketRef = useRef(null)
  const accRef = useRef('') // 当前消息累积文本
  const timerRef = useRef(null)
  const chatEndRef = useRef(null)
  const inputRef = useRef(null)

  // 初始化：拉会话列表 + 学科，选定当前会话（持久化的那个，否则新建）
  useEffect(() => {
    loadSessions()
    loadSources()
    const saved = localStorage.getItem('eduraq_session')
    // 后端 create_session 总是生成新 uuid；有存档则直接复用，无需再建
    if (saved) {
      setSessionId(saved)
      setMessages([{ role: 'assistant', text: WELCOME }])
      loadHistory(saved)
    } else {
      createSession()
    }
    return () => stop() // eslint-disable-line react-hooks/exhaustive-deps
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function createSession() {
    try {
      const r = await fetch(`${API}/api/create_session`, { method: 'POST' })
      const { session_id } = await r.json()
      localStorage.setItem('eduraq_session', session_id)
      setSessionId(session_id)
      setMessages([{ role: 'assistant', text: WELCOME }])
      loadHistory(session_id)
      loadSessions()
    } catch (e) {
      console.error('创建会话失败', e)
    }
  }

  async function loadSources() {
    try {
      const r = await fetch(`${API}/api/sources`)
      const data = await r.json()
      setSources(data.sources || [])
    } catch (e) {
      console.error('加载学科失败', e)
    }
  }

  // 拉取已有会话列表（左栏会话列表用）
  async function loadSessions() {
    try {
      const r = await fetch(`${API}/api/sessions`)
      const data = await r.json()
      setSessions(data.sessions || [])
    } catch (e) {
      console.error('加载会话列表失败', e)
    }
  }

  // 点击左栏会话，切换当前会话并加载其独立历史（会话隔离）
  function selectSession(sid) {
    if (sid === sessionId || isStreaming) return
    localStorage.setItem('eduraq_session', sid)
    setSessionId(sid)
    setMessages([{ role: 'assistant', text: WELCOME }])
    loadHistory(sid)
  }

  async function loadHistory(sid) {
    if (!sid) return
    try {
      const r = await fetch(`${API}/api/history/${sid}`)
      const { history } = await r.json()
      const msgs = [{ role: 'assistant', text: WELCOME }]
      for (const it of history || []) {
        msgs.push({ role: 'user', text: it.question })
        msgs.push({ role: 'assistant', text: it.answer })
      }
      setMessages(msgs)
    } catch (e) {
      console.error('加载历史失败', e)
    }
  }

  async function clearHistory() {
    if (!sessionId) return
    try {
      await fetch(`${API}/api/history/${sessionId}`, { method: 'DELETE' })
      setMessages([{ role: 'assistant', text: '历史已清除，有什么我可以帮您的吗？' }])
      loadSessions()
    } catch (e) {
      console.error('清除历史失败', e)
    }
  }

  function stop() {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.close()
    }
    socketRef.current = null
    flushStream()
    setIsStreaming(false)
  }

  // 节流：流式期间每 ~40ms 才把累积文本刷进 state 一次，避免每个 token 全部重渲染
  function push(text) {
    accRef.current = text
    if (timerRef.current) return
    timerRef.current = setTimeout(() => {
      timerRef.current = null
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          next[next.length - 1] = { ...last, text: accRef.current }
        }
        return next
      })
    }, 40)
  }

  function flushStream() {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last && last.role === 'assistant' && last.streaming) {
        next[next.length - 1] = { ...last, text: accRef.current, streaming: false }
      }
      return next
    })
  }

  function send() {
    const q = input.trim()
    if (!q || isStreaming) return
    setInput('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: q },
      { role: 'assistant', text: '', loading: true, streaming: true },
    ])
    accRef.current = ''

    const ws = new WebSocket(WS_BASE)
    socketRef.current = ws
    setIsStreaming(true)

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          query: q,
          source_filter: sourceFilter || null,
          session_id: sessionId,
        }),
      )
    }
    ws.onmessage = (e) => {
      let data
      try {
        data = JSON.parse(e.data)
      } catch {
        return
      }
      if (data.type === 'token') {
        push(accRef.current + data.token)
      } else if (data.type === 'end') {
        ws.close()
      } else if (data.type === 'error') {
        flushStream()
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant') {
            next[next.length - 1] = { ...last, text: `处理出错：${data.error}`, streaming: false }
          }
          return next
        })
        ws.close()
      }
    }
    ws.onclose = () => {
      // 流已结束，把累积文本收尾并停掉加载态。
      // 不在这里重载历史：问候语在后端不落库，重建会用空历史把刚回的内容清掉。
      flushStream()
      setIsStreaming(false)
      socketRef.current = null
    }
    ws.onerror = (e) => {
      console.error('WebSocket 错误', e)
      flushStream()
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, text: '连接失败，请确认服务已启动', streaming: false }
        }
        return next
      })
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // 当前会话还没产生对话时不进列表，单独作为「（新会话）」置顶展示
  const currentMissing = sessionId && !sessions.some((s) => s.session_id === sessionId)
  const sessionList = [...(currentMissing ? [{ session_id: sessionId, preview: '（新会话）' }] : []), ...sessions]

  return (
    <div className="app">
      <header className="header">
        <h1>EduRAG 智慧问答系统</h1>
        <span className="session-tag">{sessionId ? `会话 ${sessionId.slice(0, 8)}…` : '连接中…'}</span>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-actions">
            <button onClick={createSession} disabled={isStreaming}>＋ 新会话</button>
            <button onClick={clearHistory} disabled={isStreaming}>清除历史</button>
          </div>

          <div className="session-list">
            <div className="session-list-title">会话列表</div>
            <ul>
              {sessionList.map((s) => (
                <li key={s.session_id}>
                  <button
                    className={s.session_id === sessionId ? 'active' : ''}
                    onClick={() => selectSession(s.session_id)}
                    disabled={isStreaming}
                    title={s.preview}
                  >
                    <span className="s-preview">{s.preview}</span>
                    <span className="s-meta">
                      {(s.last_time || '').replace('T', ' ').slice(0, 16)} · {s.count || 1} 轮
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <label className="filter">
            学科类别
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              <option value="">全部</option>
              {sources.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        </aside>

        <main className="chat">
          <div className="messages">
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role === 'user' ? 'user' : 'assistant'}`}>
                {m.role === 'assistant' && m.loading && !m.text ? (
                  <span className="typing"><i /><i /><i /></span>
                ) : (
                  <div className="markdown" dangerouslySetInnerHTML={renderMarkdown(m.text)} />
                )}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="composer">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="请输入您的问题…（Shift+Enter 换行）"
              rows={1}
              disabled={isStreaming}
            />
            {isStreaming ? (
              <button className="stop" onClick={stop}>停止</button>
            ) : (
              <button className="send" onClick={send} disabled={!input.trim()}>发送</button>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}