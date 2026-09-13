import { IconSun, IconMoon, IconAuto } from '../lib/icons'

export default function ThemeToggle({ mode, cycle }) {
  const label = mode === 'auto' ? '跟随系统' : mode === 'light' ? '亮色' : '暗色'
  const ThemeIcon = mode === 'dark' ? IconMoon : mode === 'light' ? IconSun : IconAuto
  return (
    <button
      className="icon-btn"
      onClick={cycle}
      title={`主题：${label}`}
      aria-label={`主题：${label}，点击切换亮/暗/自动`}
    >
      <ThemeIcon />
    </button>
  )
}