import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'

// 文档详情页：承接引用溯源可视化。
// 展示全文 + 有序切块，供核对「引用溯源」的出处。
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
    return () => {
      live = false
    }
  }, [docId])

  return (
    <div className="doc-page">
      <div className="doc-toolbar">
        <Link to="/kb" className="back-link">← 返回知识库</Link>
        <span className="sub-title">文档详情</span>
      </div>
      <div className="doc-body">
        {error ? (
          <p className="kb-hint">加载失败：{error}</p>
        ) : !doc ? (
          <p className="kb-hint">加载中…</p>
        ) : (
          <>
            <h2>{doc.title}</h2>
            <p className="doc-meta">
              {doc.subject} · {doc.chunks.length} 块 · {doc.updated_at?.slice(0, 19).replace('T', ' ')}
            </p>
            <details className="doc-raw" open>
              <summary>全文（{doc.content.length} 字）</summary>
              <pre>{doc.content}</pre>
            </details>
            <h3 className="doc-chunk-title">切块（{doc.chunks.length}）</h3>
            <ul className="doc-chunks">
              {doc.chunks.map((c, i) => (
                <li key={c.id}>
                  <span className="doc-chunk-idx">{i + 1}</span>
                  <p className="doc-chunk-text">{c.text}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}