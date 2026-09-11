import { useEffect, useState, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export default function KbPage() {
  const [sources, setSources] = useState([]) // 主题/分类（来自业务库已有数据）
  const [activeKb, setActiveKb] = useState('') // 当前浏览的主题
  const [uploadSubject, setUploadSubject] = useState('') // 上传目标主题（可输入新建）
  const [keyword, setKeyword] = useState('') // 库内关键词过滤
  const [docList, setDocList] = useState([]) // 当前主题文档
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false) // 上传中
  const [uploadMsg, setUploadMsg] = useState('') // 上传态提示（成功/失败）
  const fileInputRef = useRef(null)

  async function onUploadFile(e) {
    const file = e.target.files && e.target.files[0]
    e.target.value = '' // 允许重复选同一文件
    if (!file) return
    const target = (uploadSubject && uploadSubject.trim()) || activeKb
    if (!target) {
      setUploadMsg('请填写或选择上传主题后再上传')
      return
    }
    setUploadMsg('')
    setUploading(true)
    try {
      const ret = await api.uploadDocument(file, target)
      setUploadMsg(`已上传「${ret.title}」到主题「${target}」，${ret.chunk_count} 块`)
      setActiveKb(target)
      await loadSources() // 若有新主题，让它上浮到分类栏
      loadDocs(target, keyword.trim())
    } catch (err) {
      setUploadMsg(`上传失败：${err.message}`)
    } finally {
      setUploading(false)
    }
  }

  useEffect(() => {
    loadSources()
  }, [])

  async function loadSources() {
    try {
      const list = await api.getSources()
      setSources(list || [])
      // 仅当当前浏览的主题已不存在时才回退到第一个，避免上传后刷新把选中主题冲掉
      setActiveKb((cur) => (cur && list.includes(cur)) ? cur : ((list && list[0]) || ''))
    } catch (e) {
      console.error('加载主题失败', e)
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

  // 主题切换 / 关键词变化都重新加载（关键词简单做即时请求，量小）
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
          <datalist id="subject-options">
            {sources.map((s) => <option key={s} value={s} />)}
          </datalist>
          <input
            className="kb-search kb-subject-input"
            list="subject-options"
            value={uploadSubject}
            onChange={(e) => setUploadSubject(e.target.value)}
            placeholder={activeKb ? `上传所属主题，如「${activeKb}」(可新建)` : '填写上传主题(可新建)'}
            aria-label="上传所属主题"
          />
          <input
            ref={fileInputRef}
            type="file"
            className="kb-file"
            accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.rtf,.epub,.csv,.xls,.xlsx"
            style={{ display: 'none' }}
            onChange={onUploadFile}
          />
          <button
            className="primary-btn kb-upload"
            disabled={uploading}
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
          >
            {uploading ? '上传中…' : '＋ 上传文档'}
          </button>
        </div>
      </div>

      {uploadMsg && (
        <p className="kb-upload-msg" aria-live="polite">{uploadMsg}</p>
      )}

      <div className="kb-main">
        <section className="kb-docs">
          <div className="sub-title">主题：{activeKb || '未选择'}</div>
          {loading ? (
            <p className="kb-hint">加载中…</p>
          ) : docList.length === 0 ? (
            <div className="kb-empty">
              <p>{keyword ? `「${keyword}」在 ${activeKb} 下没有匹配文档` : `该主题下暂无已入库文档`}</p>
              <p className="kb-hint">在右上输入主题（可直接填新主题），再点「＋ 上传文档」即可创建分类；这里按主题列出已入库内容。</p>
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