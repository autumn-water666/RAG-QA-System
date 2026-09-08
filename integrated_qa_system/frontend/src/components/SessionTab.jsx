export default function SessionTab({
  sessions,
  sessionId,
  sourceFilter,
  sources,
  isStreaming,
  onSelectSession,
  onCreate,
  onClear,
  onFilterChange,
  sessionList,
}) {
  return (
    <div className="tab-body">
      <div className="tab-bar-actions">
        <button onClick={onCreate} disabled={isStreaming}>＋ 新会话</button>
        <button onClick={onClear} disabled={isStreaming}>清除历史</button>
      </div>

      <span className="sub-title">会话列表</span>
      <div className="session-list">
        <ul>
          {sessionList.map((s) => (
            <li key={s.session_id}>
              <button
                className={s.session_id === sessionId ? 'active' : ''}
                onClick={() => onSelectSession(s.session_id)}
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
          {sessionList.length === 0 && <div className="kb-empty">暂无历史会话</div>}
        </ul>
      </div>

      <label className="filter">
        学科类别
        <select value={sourceFilter} onChange={(e) => onFilterChange(e.target.value)}>
          <option value="">全部</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
    </div>
  )
}