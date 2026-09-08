import SessionTab from './SessionTab'
import KbTab from './KbTab'

export default function Sidebar(props) {
  const { tab, setTab } = props
  return (
    <aside className="sidebar">
      <nav className="tabs" aria-label="主导航">
        <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>会话</button>
        <button className={tab === 'kb' ? 'active' : ''} onClick={() => setTab('kb')}>知识库</button>
      </nav>
      {tab === 'chat' ? <SessionTab {...props} /> : <KbTab {...props} />}
    </aside>
  )
}