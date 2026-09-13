import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import { IconChevronLeft, IconAlert } from '../lib/icons'

export default function DocPage() {
  const { docId } = useParams()
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    setDoc(null)
    setError('')
    api
      .getDocument(docId)
      .then((d) => live && setDoc(d))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [docId])

  if (error) {
    return (
      <div className="page"><div className="page-inner" style={{ maxWidth: 920 }}>
        <div className="empty">
          <div className="empty-icon"><IconAlert /></div>
          <div className="empty-title">加载失败</div>
          <div className="empty-sub">{error}</div>
          <div style={{ marginTop: 20 }}><Link className="btn btn-ghost" to="/kb"><IconChevronLeft /> 返回知识库</Link></div>
        </div>
      </div></div>
    )
  }

  if (!doc) {
    return (
      <div className="page"><div className="page-inner" style={{ maxWidth: 920 }}>
        <div className="empty"><div className="empty-sub">加载中…</div></div>
      </div></div>
    )
  }

  return (
    <div className="page"><div className="page-inner" style={{ maxWidth: 920 }}>
      <Link to="/kb" className="back-link" style={{ fontSize: 13, color: 'var(--text-dim)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <IconChevronLeft /> 返回知识库
      </Link>

      <div className="detail-head" style={{ marginTop: 18 }}>
        <div className="detail-title">{doc.title}</div>
        <div className="detail-meta">
          <span className="tag">{doc.subject}</span>
          <span>{doc.chunks.length} 个切块</span>
          <span>{doc.updated_at?.slice(0, 19).replace('T', ' ')}</span>
        </div>
      </div>

      <div className="detail-section-title">全文</div>
      <div className="content-box">{doc.content}</div>

      <div className="detail-section-title">切块列表（{doc.chunks.length}）</div>
      <div className="chunk-list">
        {doc.chunks.map((c, i) => (
          <div key={c.id} className="chunk">
            <div className="chunk-no">{i + 1}</div>
            <div className="chunk-body">
              <div className="chunk-text">{c.text}</div>
              {c.score != null && (
                <div style={{ marginTop: 9 }}><span className="chunk-score">命中分 {c.score}</span></div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div></div>
  )
}