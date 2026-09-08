// 设置页：主题 / 后端连接状态 / 索引维护（后端接口待接）
export default function SettingsPage({ theme }) {
  return (
    <div className="settings-page">
      <h2>设置</h2>

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
          onClick={() => console.warn('[待后端] 重建索引接口尚未实现')}
        >
          重建知识库索引
        </button>
        <p className="kb-hint">危险操作，需二次确认。接口接入后再启用。</p>
      </section>
    </div>
  )
}