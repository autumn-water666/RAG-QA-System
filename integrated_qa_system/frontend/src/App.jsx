import { useEffect, useRef, useState } from 'react'
import { useTheme } from './theme'
import Sidebar from './components/Sidebar'
import MessageBubble from './components/MessageBubble'
import Composer from './components/Composer'
import ThemeToggle from './components/ThemeToggle'

// 前后端同域部署（FastAPI 托管前端），API 均为相对路径。
// 全部会话走 WebSocket 单通道：问候 / BM25 快答 / RAG 流式由后端统一返回 token。
const API = ''
const WS_BASE =
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/stream`

const WELCOME = '您好！我是智能问答助手，有什么我可以帮您的吗？'

export default function App() {
  const { mode, cycle } = useTheme()

  const [sessionId, setSessionId] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sources, setSources] = useState([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [tab, setTab] = useState('chat')
  const [activeKb, setActiveKb] = useState(null)
  const [echoOn, setEchoOn] = useState(true) // 续文追问：带本轮上下文
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

  const socketRef = useRef(null)
  const accRef = useRef('') // 当前消息累积文本
  const timerRef = useRef(null)
  const chatEndRef = useRef(null)
  const idRef = useRef(0)

  const nextId = () => `m${++idRef.current}`

  // 初始化：拉会话列表 + 学科，选定当前会话（持久化的那个，否则新建）
  useEffect(() => {
    loadSessions()
    loadSources()
    const saved = localStorage.getItem('eduraq_session')
    if (saved) {
      setSessionId(saved)
      setMessages([{ id: nextId(), role: 'assistant', text: WELCOME }])
      loadHistory(saved)
    } else {
      createSession()
    }
    return () => stop() // eslint-disable-line react-hooks/exhaustive-deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadSessions() {
    try {
      const r = await fetch(`${API}/api/sessions`)
      const data = await r.json()
      setSessions(data.sessions || [])
    } catch (e) {
      console.error('加载会话列表失败', e)
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

  async function loadHistory(sid) {
    if (!sid) return
    try {
      const r = await fetch(`${API}/api/history/${sid}`)
      const { history } = await r.json()
      const msgs = [{ id: nextId(), role: 'assistant', text: WELCOME, sources: [] }]
      for (const it of history || []) {
        msgs.push({ id: nextId(), role: 'user', text: it.question })
        msgs.push({ id: nextId(), role: 'assistant', text: it.answer, sources: it.sources || [] })
      }
      setMessages(msgs)
    } catch (e) {
      console.error('加载历史失败', e)
    }
  }

  async function createSession() {
    try {
      const r = await fetch(`${API}/api/create_session`, { method: 'POST' })
      const { session_id } = await r.json()
      localStorage.setItem('eduraq_session', session_id)
      setSessionId(session_id)
      setMessages([{ id: nextId(), role: 'assistant', text: WELCOME, sources: [] }])
      loadHistory(session_id)
      loadSessions()
    } catch (e) {
      console.error('创建会话失败', e)
    }
  }

  function selectSession(sid) {
    if (sid === sessionId || isStreaming) return
    localStorage.setItem('eduraq_session', sid)
    setSessionId(sid)
    setMessages([{ id: nextId(), role: 'assistant', text: WELCOME, sources: [] }])
    loadHistory(sid)
  }

  async function clearHistory() {
    if (!sessionId || isStreaming) return
    try {
      await fetch(`${API}/api/history/${sessionId}`, { method: 'DELETE' })
      setMessages([{ id: nextId(), role: 'assistant', text: '历史已清除，有什么我可以帮您的吗？', sources: [] }])
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

  // 节流：流式期间每 ~40ms 才把累积文本刷进 state 一次
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
        next[next.length - 1] = { ...last, text: accRef.current, streaming: false, loading: false }
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
      { id: nextId(), role: 'user', text: q },
      { id: nextId(), role: 'assistant', text: '', loading: true, streaming: true, sources: [] },
    ])
    accRef.current = ''

    const ws = new WebSocket(WS_BASE)
    socketRef.current = ws
    setIsStreaming(true)

    ws.onopen = () => {
      // 续文追问关闭时：session_id 置空 → 后端不带上文、也不写入该会话，按独立问题处理
      ws.send(
        JSON.stringify({
          query: q,
          source_filter: sourceFilter || null,
          session_id: echoOn ? sessionId : null,
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
        // 后端若在 end 里带 sources（引用溯源），挂到本条回答上
        if (data.sources) {
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last && last.role === 'assistant') {
              next[next.length - 1] = { ...last, sources: data.sources }
            }
            return next
          })
        }
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
      // 流已结束：收尾停加载态，刷新会话列表（预览/时间会变）
      flushStream()
      setIsStreaming(false)
      socketRef.current = null
      loadSessions()
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

  // 当前会话还没产生对话时不进列表，单独作为「（新会话）」置顶展示
  const currentMissing = sessionId && !sessions.some((s) => s.session_id === sessionId)
  const sessionList = [
    ...(currentMissing ? [{ session_id: sessionId, preview: '（新会话）' }] : []),
    ...sessions,
  ]

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo">R</span>
          <h1>EduRAG 智慧问答系统</h1>
        </div>
        <div className="header-right">
          <span className="session-tag">
            {sessionId ? `会话 ${sessionId.slice(0, 8)}…` : '连接中…'}
          </span>
          <ThemeToggle mode={mode} cycle={cycle} />
        </div>
      </header>

      <div className="layout">
        <Sidebar
          tab={tab}
          setTab={setTab}
          sessions={sessions}
          sessionId={sessionId}
          sessionList={sessionList}
          sourceFilter={sourceFilter}
          sources={sources}
          isStreaming={isStreaming}
          onSelectSession={selectSession}
          onCreate={createSession}
          onClear={clearHistory}
          onFilterChange={setSourceFilter}
          activeKb={activeKb}
          onSelectKb={setActiveKb}
          onUpload={() => console.warn('[待后端] 上传文档接口尚未实现')}
        />

        <main className="chat">
          <div className="messages">
            {messages.map((m) => (
              <MessageBubble key={m.id} msg={m} />
            ))}
            <div ref={chatEndRef} />
          </div>

          <Composer
            input={input}
            setInput={setInput}
            isStreaming={isStreaming}
            onSend={send}
            onStop={stop}
            echoOn={echoOn}
            setEchoOn={setEchoOn}
          />
        </main>
      </div>
    </div>
  )
}