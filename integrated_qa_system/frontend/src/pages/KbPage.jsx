import { useEffect, useState, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useToast } from '../components/Toast'
import {
  IconSearch, IconUpload, IconTrash, IconFolder,
  IconCheck, IconClock, IconAlert,
} from '../lib/icons'

const ACCEPT = '.txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.rtf,.epub,.csv,.xls,.xlsx'

function fmtTime(iso) {
  if (!iso) return ''
  return iso.slice(0, 19).replace('T', ' ')
}

export default function KbPage() {
  const toast = useToast()
  const [sources, setSources] = useState([]) // 主题列表
  const [activeKb, setActiveKb] = useState('') // 当前浏览主题
  const [uploadSubject, setUploadSubject] = useState('') // 上传目标主题（可输入新建）
  const [keyword, setKeyword] = useState('') // 库内关键词过滤
  const [docList, setDocList] = useState([]) // 当前主题文档
  const [subjectCounts, setSubjectCounts] = useState({}) // 每个主题文档数
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadJob, setUploadJob] = useState(null) // 上传任务进度（UploadStatus）
  const fileInputRef = useRef(null)
  const pollRef = useRef(null)
  const hideRef = useRef(null)

  function stopPolling() {
    if (pollRef.current) {
      clearTimeout(pollRef.current)
      pollRef.current = null
    }
  }

  async function pollUpload(jobId, interval) {
    try {
      const s = await api.uploadStatus(jobId)
      setUploadJob(s)
      if (s.finished) {
        stopPolling()
        setUploading(false)
        const failed = s.failed
        toast(failed ? 'error' : 'success',
          failed ? `上传完成：成功 ${s.done}/${s.total}，失败 ${failed} 个` : `上传完成：${s.done} 个文件已入库`)
        if (!failed) {
          setUploadSubject('')
          await loadSources()
          loadDocs(activeKb, keyword.trim())
        } else {
          loadSources()
        }
        // 完成后稍候自动收起上传面板
        hideRef.current = setTimeout(() => setUploadJob(null), 5000)
        return
      }
    } catch (e) {
      console.error('查询上传进度失败', e)
      stopPolling()
      setUploading(false)
      return
    }
    pollRef.current = setTimeout(() => pollUpload(jobId, interval), interval)
  }

  useEffect(() => () => { stopPolling(); if (hideRef.current) clearTimeout(hideRef.current) }, [])

  useEffect(() => {
    loadSources()
  }, [])

  async function loadSources() {
    try {
      const list = await api.getSources()
      setSources(list || [])
      // 刷新每个主题的文档数（用于主题标签角标）
      if (list && list.length) {
        const entries = await Promise.all(
          list.map(async (s) => [s, (await api.getDocuments(s).catch(() => [])).length]),
        )
        setSubjectCounts(Object.fromEntries(entries))
      }
      // 仅当当前浏览的主题已不存在时才回退到第一个
      setActiveKb((cur) => (cur && list.includes(cur)) ? cur : ((list && list[0]) || ''))
    } catch (e) {
      toast.error(`加载主题失败：${e.message || e}`, 4000)
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
      toast.error(`加载文档失败：${e.message || e}`, 4000)
      setDocList([])
    } finally {
      setLoading(false)
    }
  }, [])

  // 主题切换 / 关键词变化都重新加载（关键词做短延时请求）
  useEffect(() => {
    const t = setTimeout(() => loadDocs(activeKb, keyword.trim()), keyword ? 300 : 0)
    return () => clearTimeout(t)
  }, [activeKb, keyword, loadDocs])

  function switchSubject(s) {
    setActiveKb(s)
    setKeyword('')
  }

  async function onUploadFile(e) {
    const files = e.target.files ? Array.from(e.target.files) : []
    e.target.value = '' // 允许重复选同一文件
    if (!files.length) return
    const target = (uploadSubject && uploadSubject.trim()) || activeKb
    if (!target) {
      toast.error('请填写或选择上传主题后再上传')
      return
    }
    stopPolling()
    if (hideRef.current) { clearTimeout(hideRef.current); hideRef.current = null }
    setUploading(true)
    setUploadJob(null)
    try {
      const { job_id, total } = await api.uploadDocuments(files, target)
      // 先立一个“排队中”的面板
      setUploadJob({
        subject: target, total, done: 0, failed: 0, finished: false,
        items: files.map((f) => ({ file: f.name, status: 'pending', message: '', title: '', chunk_count: 0 })),
      })
      setActiveKb(target)
      pollUpload(job_id, 1200)
    } catch (err) {
      toast.error(`上传提交失败：${err.message || err}`)
      setUploading(false)
    }
  }

  async function deleteDoc(docId) {
    const doc = docList.find((d) => d.id === docId)
    if (!window.confirm(`确定删除《${doc?.title || docId}》？此操作不可撤销。`)) return
    try {
      await api.deleteDocument(docId)
      toast.success('文档已删除')
      loadSources()
      loadDocs(activeKb, keyword.trim())
    } catch (e) {
      toast.error(`删除失败：${e.message || e}`)
    }
  }

  const totalCount = Object.values(subjectCounts).reduce((a, b) => a + b, 0)

  return (
    <div className="page"><div className="page-inner">
      <div className="page-head">
        <div>
          <div className="page-title">知识库</div>
          <div className="page-sub">共 {totalCount} 篇文档 · {sources.length} 个主题</div>
        </div>
      </div>

      <div className="subject-tabs">
        {sources.map((s) => (
          <button
            key={s}
            className={`subject-tab${activeKb === s ? ' active' : ''}`}
            onClick={() => switchSubject(s)}
          >
            {s}<span className="cnt">{subjectCounts[s] || 0}</span>
          </button>
        ))}
      </div>

      <div className="kb-toolbar">
        <div className="search-wrap">
          <span className="search-icon"><IconSearch /></span>
          <input
            className="field"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="在库内搜索文档标题…"
            aria-label="库内搜索"
          />
        </div>
        <div className="spacer" />
        <input
          className="field upload-subject"
          list="subject-suggest"
          value={uploadSubject}
          onChange={(e) => setUploadSubject(e.target.value)}
          placeholder={activeKb ? `上传主题（如「${activeKb}」，可新建）` : '上传主题（可新建）'}
          aria-label="上传所属主题"
        />
        <datalist id="subject-suggest">
          {sources.map((s) => <option key={s} value={s} />)}
        </datalist>
        <button
          className="btn btn-primary"
          id="upload-btn"
          disabled={uploading}
          onClick={() => fileInputRef.current && fileInputRef.current.click()}
        >
          <IconUpload /> {uploading ? '处理中…' : '上传文档'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          accept={ACCEPT}
          onChange={onUploadFile}
        />
      </div>

      {uploadJob && <UploadPanel job={uploadJob} />}

      {loading ? (
        <div className="empty"><div className="empty-sub">加载中…</div></div>
      ) : docList.length === 0 ? (
        <div className="empty">
          <div className="empty-icon"><IconFolder /></div>
          <div className="empty-title">{keyword ? '没有匹配的文档' : `「${activeKb}」下还没有文档`}</div>
          <div className="empty-sub">
            {keyword
              ? '换一个关键词试试，或清空搜索框查看全部。'
              : '在上方填写主题并点击「上传文档」。上传后系统会自动切块、向量化并入库。'}
          </div>
        </div>
      ) : (
        <div className="doc-grid">
          {docList.map((d) => (
            <Link key={d.id} to={`/kb/${d.id}`} className="doc-card">
              <button
                className="doc-del"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); deleteDoc(d.id) }}
                title="删除文档"
                aria-label="删除文档"
              >
                <IconTrash />
              </button>
              <div className="doc-card-title">{d.title}</div>
              <div><span className="tag">{d.subject}</span></div>
              <div className="doc-card-foot">
                <span>{d.chunk_count} 个切块</span>
                {fmtTime(d.updated_at) && <>
                  <span>·</span>
                  <span>{fmtTime(d.updated_at)}</span>
                </>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div></div>
  )
}

function UploadPanel({ job }) {
  const pct = job.total ? Math.round(((job.done + job.failed) / job.total) * 100) : 0
  return (
    <div className="upload-panel">
      <div className="upload-head">
        <div className="upload-title">
          <span className="svg-ic">{job.finished ? <IconCheck /> : <IconClock />}</span>
          上传任务
          <span className="tag">{job.subject}</span>
        </div>
        <div className="upload-progress-text">
          {job.finished ? '已完成' : `正在处理 ${job.done + job.failed}/${job.total}`}
          · 成功 {job.done} · 失败 {job.failed}
        </div>
      </div>
      <div className="progress-bar">
        <div className={`progress-fill${job.finished ? ' done' : ''}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="upload-items">
        {job.items.map((it, i) => (
          <div key={i} className="upload-item">
            <span className={`dot ${it.status}`} />
            <span className="upload-item-name">{it.file}</span>
            {it.status === 'error'
              ? <span className="upload-msg" title={it.message}>{it.message || '处理失败'}</span>
              : it.status === 'done'
                ? <span className="upload-ok">{it.chunk_count} 切块</span>
                : <span className="upload-ok">{it.status === 'processing' ? '处理中…' : '排队中'}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}