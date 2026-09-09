// 设置页：意图识别开关 / 后端连接状态 / 索引维护
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function SettingsPage({ theme }) {
  const [intent, setIntent] = useState(null) // null=加载中
  const [loadErr, setLoadErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildMsg, setRebuildMsg] = useState('')

  // 进入页面加载当前开关状态
  useEffect(() => {
    let alive = true
    api.getIntentClassify()
      .then((v) => alive && setIntent(v))
      .catch((e) => alive && setLoadErr(String(e.message || e)))
    return () => { alive = false }
  }, [])

  // 重建知识库索引（危险操作，弹窗确认）
  async function handleRebuild() {
    if (!window.confirm('确定重建整个知识库索引？现有向量数据会被覆盖重建，此操作不可撤销。')) return
    setRebuilding(true)
    setRebuildMsg('')
    try {
      const r = await api.rebuildIndex()
      setRebuildMsg(`重建完成：${r.status || 'OK'}`)
    } catch (e) {
      setRebuildMsg(`重建失败：${e.message || e}`)
    } finally {
      setRebuilding(false)
    }
  }

  // 切换开关：调后端运行时重编译编排图，立即生效
  async function toggleIntent() {
    const next = !intent
    setSaving(true)
    setSaveMsg('')
    try {
      const v = await api.setIntentClassify(next)
      setIntent(v)
      setSaveMsg(v ? '已开启：按「通用知识 / 专业咨询」路由。' : '已关闭：所有问题一律走检索。')
    } catch (e) {
      setSaveMsg(`切换失败：${e.message || e}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-page">
      <h2>设置</h2>

      <section className="card">
        <h3>问答智能</h3>
        <div className="settings-row">
          <div>
            <label>意图识别</label>
            <p className="kb-hint">
              开启后系统先把问题分为「通用知识 / 专业咨询」再路由：
              通用知识直接走大模型，专业咨询才检索知识库。
              关闭后所有问题一律走知识库检索（RAG）。
            </p>
          </div>
          <button
            className={`toggle ${intent ? 'on' : 'off'}`}
            onClick={toggleIntent}
            disabled={saving || intent === null}
            aria-pressed={intent}
            aria-label="意图识别开关"
          >
            {intent === null ? '…' : intent ? '开' : '关'}
          </button>
        </div>
        {loadErr && <p className="kb-upload-msg error">{loadErr}</p>}
        {saveMsg && <p className="kb-upload-msg">{saveMsg}</p>}
      </section>

      <section className="card">
        <h3>外观</h3>
        <p className="kb-hint">
          当前主题：<strong>{theme === 'dark' ? '墨绿深色' : '蓝白浅色'}</strong>。
          右上角按钮切换（自动跟随系统 / 浅色 / 深色三态循环）。
        </p>
      </section>

      <section className="card">
        <h3>后端连接</h3>
        <ul className="settings-list">
          <li>接口基础路径 <code>${''}</code>（同域部署）</li>
          <li>状态检测接口待接入 <code>GET /health</code></li>
        </ul>
      </section>

      <section className="card">
        <h3>维护</h3>
        <button
          className="danger-btn"
          onClick={handleRebuild}
          disabled={rebuilding}
        >
          {rebuilding ? '重建中…' : '重建知识库索引'}
        </button>
        <p className="kb-hint">
          重扫 data 目录全部原始文档，重新分块 + 向量化并幂等写入向量库。
          耗时取决于文档量，期间可正常检索。危险操作，需二次确认。
        </p>
        {rebuildMsg && <p className="kb-upload-msg">{rebuildMsg}</p>}
      </section>
    </div>
  )
}