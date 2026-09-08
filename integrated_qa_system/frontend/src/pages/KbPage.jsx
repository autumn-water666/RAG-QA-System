import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function KbPage() {
  const [sources, setSources] = useState([])
  const [activeKb, setActiveKb] = useState('') // 当前学科
  const [keyword, setKeyword] = useState('') // 库内搜索（待后端）
  const [preview, setPreview] = useState(null) // 文档预览抽屉

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

  // 后端文档接口待接：/api/kb/documents?subject=xxx → 渲染 docList
  const docList = [] // stub

  return (
    <div className="kb-page">
      <div className="kb-toolbar">
        <div className="kb-subject-tabs">
          {sources.map((s) => (
            <button
              key={s}
              className={activeKb === s ? 'active' : ''}
              onClick={() => setActiveKb(s)}
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
            placeholder="搜索库内内容…（待后端接入）"
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
          {docList.length === 0 ? (
            <div className="kb-empty">
              <p>该学科下暂无已入库文档</p>
              <p className="kb-hint">知识库文档目录接口待后端接入后，这里按学科展示已入库内容并支持增量索引。</p>
            </div>
          ) : (
            <ul className="doc-list">
              {docList.map((d) => (
                <li key={d.id}>
                  <button className="doc-card" onClick={() => setPreview(d)}>
                    <span className="doc-title">{d.title}</span>
                    <span className="doc-meta">{d.subject || activeKb} · {d.updatedAt}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {preview && (
          <aside className="kb-preview">
            <button className="kb-preview-close" onClick={() => setPreview(null)} aria-label="关闭预览">×</button>
            <h3>{preview.title}</h3>
            <p className="doc-meta">{preview.subject} · 持续更新</p>
            <div className="kb-preview-body">
              <p className="kb-hint">文档全文与命中片段高亮待后端文档详情接口接入。</p>
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}