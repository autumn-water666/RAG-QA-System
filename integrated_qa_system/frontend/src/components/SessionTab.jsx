import { IconPlus, IconTrash } from '../lib/icons'

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前'
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return hm
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}

export default function SessionTab({
  sessionList,
  sessionId,
  sourceFilter,
  sources,
  followUp,
  isStreaming,
  onSelectSession,
  onCreate,
  onClear,
  onFilterChange,
  onFollowUpChange,
}) {
  // 按时间倒序
  const sorted = [...sessionList].sort(
    (a, b) => new Date(b.last_time || 0) - new Date(a.last_time || 0),
  )

  return (
    <>
      <div className="side-head">
        <button className="btn btn-primary btn-sm" onClick={onCreate} disabled={isStreaming}>
          <IconPlus /> 新建会话
        </button>
        <div className="side-title">会话列表</div>
      </div>

      <div className="session-list">
        {sorted.length === 0 ? (
          <div style={{ padding: '28px 14px', textAlign: 'center', color: 'var(--text-mute)', fontSize: '12.5px' }}>
            暂无会话
          </div>
        ) : (
          sorted.map((s) => (
            <div
              key={s.session_id}
              className={`session-item${s.session_id === sessionId ? ' active' : ''}`}
              onClick={() => !isStreaming && onSelectSession(s.session_id)}
            >
              <div className="session-preview">{s.preview || '新会话'}</div>
              <div className="session-meta">
                <span>{s.count || 1} 轮</span>
                {fmtTime(s.last_time) && <span>{fmtTime(s.last_time)}</span>}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="side-foot">
        <div className="opt-row">
          <span className="opt-label">主题过滤</span>
          <select
            className="select-sm"
            value={sourceFilter}
            onChange={(e) => onFilterChange(e.target.value)}
            aria-label="主题过滤"
          >
            <option value="">全部</option>
            {sources.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="opt-row">
          <span className="opt-label">续文追问</span>
          <div
            className={`switch${followUp ? ' on' : ''}`}
            role="switch"
            aria-checked={followUp}
            aria-label="续文追问"
            onClick={() => onFollowUpChange(!followUp)}
          />
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onClear}
          disabled={isStreaming}
          style={{ width: '100%' }}
        >
          <IconTrash /> 清除会话历史
        </button>
      </div>
    </>
  )
}