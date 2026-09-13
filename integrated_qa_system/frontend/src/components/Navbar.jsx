import { NavLink } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'

export default function Navbar({ mode, cycle }) {
  return (
    <header className="nav">
      <div className="logo">
        <div className="mark">R</div>
        <span>智能问答系统</span>
      </div>
      <NavLink to="/" end className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}>
        对话
      </NavLink>
      <NavLink to="/kb" className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}>
        知识库
      </NavLink>
      <NavLink to="/settings" className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}>
        设置
      </NavLink>
      <div className="nav-spacer" />
      <ThemeToggle mode={mode} cycle={cycle} />
    </header>
  )
}