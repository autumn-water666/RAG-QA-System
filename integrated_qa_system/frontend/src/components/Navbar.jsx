import { NavLink } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'

export default function Navbar({ mode, cycle }) {
  return (
    <header className="navbar">
      <div className="brand">
        <span className="logo">R</span>
        <h1>EduRAG 智慧问答系统</h1>
      </div>
      <nav className="main-nav">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          工作台
        </NavLink>
        <NavLink to="/kb" className={({ isActive }) => (isActive ? 'active' : '')}>
          知识库
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => (isActive ? 'active' : '')}>
          设置
        </NavLink>
      </nav>
      <div className="header-right">
        <ThemeToggle mode={mode} cycle={cycle} />
      </div>
    </header>
  )
}