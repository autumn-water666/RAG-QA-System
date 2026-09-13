import { useRef } from 'react'
import { IconSend, IconStop } from '../lib/icons'

export default function Composer({ input, setInput, isStreaming, onSend, onStop, followUp, sourceFilter }) {
  const taRef = useRef(null)

  function autoGrow() {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 150) + 'px'
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !isStreaming) onSend()
    }
  }

  const scope = sourceFilter ? `检索范围：${sourceFilter}` : '检索范围：全库'
  const hint = `${followUp ? '续文追问：开（携带上下文）' : '续文追问：关（独立提问，不写入历史）'} · ${scope}`

  return (
    <div className="composer">
      <div className="composer-inner">
        <textarea
          ref={taRef}
          value={input}
          onChange={(e) => { setInput(e.target.value); autoGrow() }}
          onKeyDown={onKeyDown}
          placeholder="输入问题，Enter 发送 / Shift+Enter 换行…"
          rows={1}
          aria-label="问题输入框"
        />
        {isStreaming ? (
          <button className="send-btn stop-btn" onClick={onStop} aria-label="停止生成">
            <IconStop />
          </button>
        ) : (
          <button className="send-btn" onClick={onSend} disabled={!input.trim()} aria-label="发送">
            <IconSend />
          </button>
        )}
      </div>
      <div className="composer-hint">{hint}</div>
    </div>
  )
}