import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export default function KbPage() {
  const [sources, setSources] = useState([])
  const [activeKb, setActiveKb] = useState('') // 当前学科
  const [keyword, setKeyword] = useState('') // 库内关键词过滤
  const [docList, setDocList] = useState([]) // 当前学科文档
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadSources()
  }, [])

  async function loadSources() {
    try {
      const list = await api.getSources()
      setSources(list || [])
      if (list && list.length) setActiveKb(list[0])
    } catch (e) {
      console.error('加载学科失败', e)
    }
  }

  const loadDocs = useCallback(async (subject, q) => {
    if (!subject) {
      setDocList([])
      return
    }
    setLoading(true)
    try {
      const list = await api.getDocuments(subject, q)
      setDocList(list || [])
    } catch (e) {
      console.error('加载文档失败', e)
      setDocList([])
    } finally {
      setLoading(false)
    }
  }, [])

  // 学科切换 / 关键词变化都重新加载（关键词简单做即时请求，量小）
  useEffect(() => {
    const t = setTimeout(() => loadDocs(activeKb, keyword.trim()), keyword ? 300 : 0)
    return () => clearTimeout(t)
  }, [activeKb, keyword, loadDocs])

  function switchSubject(s) {
    setActiveKb(s)
    setKeyword('')
  }

  return (
    <div className="kb-page">
      <div className="kb-toolbar">
        <div className="kb-subject-tabs">
          {sources.map((s) => (
            <button
              key={s}
              className={activeKb === s ? 'active' : ''}
              onClick={() => switchSubject(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="kb-toolbar-right">
          <input
            className="kb-search"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder={`在 ${activeKb || '知识库'} 内搜索…`}
            aria-label="库内搜索"
          />
          <button
            className="primary-btn kb-upload"
            onClick={() => console.warn('[待后端] 上传文档接口尚未实现')}
          >
            ＋ 上传文档
          </button>
        </div>
      </div>

      <div className="kb-main">
        <section className="kb-docs">
          <div className="sub-title">学科：{activeKb || '未选择'}</div>
          {loading ? (
            <p className="kb-hint">加载中…</p>
          ) : docList.length === 0 ? (
            <div className="kb-empty">
              <p>{keyword ? `「${keyword}」在 ${activeKb} 下没有匹配文档` : `该学科下暂无已入库文档`}</p>
              <p className="kb-hint">上传文档走「＋ 上传文档」；这里按学科列出已入库内容。</p>
            </div>
          ) : (
            <ul className="doc-list">
              {docList.map((d) => (
                <li key={d.id}>
                  <Link className="doc-card" to={`/kb/${d.id}`}>
                    <span className="doc-title">{d.title}</span>
                    <span className="doc-meta">
                      {d.subject} · {d.chunk_count} 块 · {d.updated_at?.slice(0, 19).replace('T', ' ')}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}