import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import SessionTab from '../components/SessionTab'
import MessageBubble from '../components/MessageBubble'
import Composer from '../components/Composer'

const WELCOME = '您好！我是智能问答助手，有什么我可以帮您的吗？'

export default function Workspace() {
  const [sessionId, setSessionId] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sources, setSources] = useState([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [echoOn, setEchoOn] = useState(true)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

  const socketRef = useRef(null)
  const accRef = useRef('')
  const timerRef = useRef(null)
  const chatEndRef = useRef(null)
  const idRef = useRef(0)
  const nextId = () => `m${++idRef.current}`

  useEffect(() => {
    loadSessions()
    loadSources()
    const saved = localStorage.getItem('eduraq_session')
    if (saved) {
      setSessionId(saved)
      setMessages([{ id: nextId(), role: 'assistant', text: WELCOME, sources: [] }])
      loadHistory(saved)
    } else {
      createSession()
    }
    return () => stop() // eslint-disable-line react-hooks/exhaustive-deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadSessions() {
    try {
      const list = await api.getSessions()
      setSessions(list || [])
    } catch (e) {
      console.error('加载会话列表失败', e)
    }
  }

  async function loadSources() {
    try {
      const list = await api.getSources()
      setSources(list || [])
    } catch (e) {
      console.error('加载学科失败', e)
    }
  }

  async function loadHistory(sid) {
    if (!sid) return
    try {
      const history = await api.getHistory(sid)
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
      const { session_id } = await api.createSession()
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
      await api.clearHistory(sessionId)
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

    const ws = new WebSocket(api.wsStreamUrl())
    socketRef.current = ws
    setIsStreaming(true)

    ws.onopen = () => {
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
        if (data.sources) {
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last && last.role === 'assistant') next[next.length - 1] = { ...last, sources: data.sources }
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

  const currentMissing = sessionId && !sessions.some((s) => s.session_id === sessionId)
  const sessionList = [
    ...(currentMissing ? [{ session_id: sessionId, preview: '（新会话）' }] : []),
    ...sessions,
  ]

  return (
    <div className="layout">
      <aside className="sidebar">
        <SessionTab
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
        />
      </aside>

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
  )
}