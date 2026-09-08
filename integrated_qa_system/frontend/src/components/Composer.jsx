function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M3.4 20.4l17.5-7.5a1 1 0 000-1.8L3.4 3.6a1 1 0 00-1.4 1.1l1.5 5.2 9 2.1-9 2.1-1.5 5.2a1 1 0 001.4 1.1z" />
    </svg>
  )
}
function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  )
}

export default function Composer({ input, setInput, isStreaming, onSend, onStop, echoOn, setEchoOn }) {
  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !isStreaming) onSend()
    }
  }

  return (
    <div className="composer">
      <div className="composer-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="请输入您的问题…（Shift+Enter 换行）"
          rows={1}
          disabled={isStreaming}
          aria-label="问题输入框"
        />
        {isStreaming ? (
          <button className="primary-btn stop-btn" onClick={onStop} aria-label="停止生成">停止</button>
        ) : (
          <button className="primary-btn" onClick={onSend} disabled={!input.trim()}>发送</button>
        )}
      </div>
      <div className="composer-inline">
        <label className="echo-toggle" title="关闭后按独立问题检索，不结合上轮上下文">
          <input
            type="checkbox"
            checked={echoOn}
            onChange={(e) => setEchoOn(e.target.checked)}
            disabled={isStreaming}
          />
          续文追问（结合上文）
        </label>
      </div>
    </div>
  )
}