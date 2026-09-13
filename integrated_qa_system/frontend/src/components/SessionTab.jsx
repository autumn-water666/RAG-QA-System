// 按时间把会话分组：今天 / 昨天 / 更早。无 last_time 的合成项（当前新会话）视为今天。
function toKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function historyGroups(items) {
  const now = new Date()
  const todayKey = toKey(now)
  const yestKey = toKey(new Date(now.getTime() - 86400000))
  const buckets = [['今天', []], ['昨天', []], ['更早', []]]
  for (const it of items) {
    const t = it.last_time ? new Date(it.last_time) : null
    const k = t && !isNaN(t) ? toKey(t) : todayKey
    if (k === todayKey) buckets[0][1].push(it)
    else if (k === yestKey) buckets[1][1].push(it)
    else buckets[2][1].push(it)
  }
  return buckets.filter(([, list]) => list.length)
}

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
  const groups = historyGroups(sessionList)

  return (
    <div className="tab-body">
      <div className="tab-bar-actions">
        <button onClick={onCreate} disabled={isStreaming}>＋ 新会话</button>
        <button onClick={onClear} disabled={isStreaming}>清除历史</button>
      </div>

      <span className="sub-title">会话列表</span>
      <div className="session-list">
        {groups.length === 0 ? (
          <div className="kb-empty">暂无历史会话</div>
        ) : (
          groups.map(([label, list], gi) => (
            <div key={label} className="session-group">
              <div className="session-group-title">{label}</div>
              <ul>
                {list.map((s) => (
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
              </ul>
            </div>
          ))
        )}
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