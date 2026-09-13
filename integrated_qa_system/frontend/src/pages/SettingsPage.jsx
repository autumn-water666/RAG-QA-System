// 设置页：意图识别开关（设计稿核心）+ 索引维护
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../components/Toast'

export default function SettingsPage({ theme }) {
  const toast = useToast()
  const [intent, setIntent] = useState(null) // null=加载中
  const [rebuilding, setRebuilding] = useState(false)

  // 进入页面加载当前开关状态
  useEffect(() => {
    let alive = true
    api.getIntentClassify()
      .then((v) => alive && setIntent(v))
      .catch((e) => alive && toast.error(`读取意图识别开关失败：${e.message || e}`))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 切换开关：调后端运行时重编译编排图，立即生效
  async function toggleIntent() {
    const next = !intent
    try {
      const v = await api.setIntentClassify(next)
      setIntent(v)
      toast.success(v ? '意图识别已开启：按「通用知识 / 专业咨询」路由。' : '意图识别已关闭：所有问题一律走检索。')
    } catch (e) {
      toast.error(`切换失败：${e.message || e}`)
    }
  }

  // 重建知识库索引（危险操作，弹窗确认）
  async function handleRebuild() {
    if (!window.confirm('确定重建整个知识库索引？现有向量数据会被覆盖重建，此操作不可撤销。')) return
    setRebuilding(true)
    try {
      const r = await api.rebuildIndex()
      toast.success(`重建完成：${r.status || 'OK'}（共 ${r.total_chunks ?? '?'} 块）`)
    } catch (e) {
      toast.error(`重建失败：${e.message || e}`)
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="page"><div className="page-inner settings-wrap">
      <div className="page-head">
        <div>
          <div className="page-title">设置</div>
          <div className="page-sub">运行时配置，修改后立即生效</div>
        </div>
      </div>

      <div className="setting-card">
        <div>
          <div className="setting-name">意图识别</div>
          <div className="setting-desc">
            开启后，后端会先判断问题属于「通用闲聊」还是「专业咨询」，再决定是否走知识库检索流程。
            关闭则所有问题都按专业咨询处理（始终检索）。
          </div>
        </div>
        <div
          className={`switch${intent ? ' on' : ''}`}
          role="switch"
          aria-checked={!!intent}
          aria-label="意图识别开关"
          onClick={intent === null ? undefined : toggleIntent}
        />
      </div>

      <div style={{ marginTop: 16, fontSize: 12.5, color: 'var(--text-mute)' }}>
        当前状态：
        <strong style={{ color: 'var(--text)' }}>{intent === null ? '加载中…' : (intent ? '已开启' : '已关闭')}</strong>
        {intent === null ? '' : ' · 对应接口 GET/POST /api/settings/intent'}
      </div>

      <div className="setting-card" style={{ marginTop: 28 }}>
        <div>
          <div className="setting-name">重建知识库索引</div>
          <div className="setting-desc">
            重扫 data 目录全部原始文档，重新分块 + 向量化并幂等写入向量库。危险操作，需二次确认。
          </div>
        </div>
        <button className="btn btn-ghost" onClick={handleRebuild} disabled={rebuilding}>
          {rebuilding ? '重建中…' : '重建索引'}
        </button>
      </div>

      <div style={{ marginTop: 28 }}>
        <div className="setting-card">
          <div>
            <div className="setting-name">外观</div>
            <div className="setting-desc">
              当前主题：<strong>{theme === 'dark' ? '暗色' : '亮色'}</strong>。
              右上角按钮切换（自动跟随系统 / 亮色 / 暗色三态循环）。
            </div>
          </div>
        </div>
      </div>
    </div></div>
  )
}