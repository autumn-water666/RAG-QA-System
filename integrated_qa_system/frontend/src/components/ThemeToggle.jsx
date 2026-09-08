// SVG 图标：深色=月亮，浅色=太阳，auto=半日半月。不用 emoji。
const Sun = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
)
const Moon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
)
const Auto = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1" />
  </svg>
)

export default function ThemeToggle({ mode, cycle }) {
  const label = mode === 'auto' ? '随系统' : mode === 'light' ? '浅色' : '深色'
  const Icon = mode === 'dark' ? Moon : mode === 'light' ? Sun : Auto
  return (
    <button
      className="theme-toggle"
      onClick={cycle}
      title={`主题：${label}（点击切换）`}
      aria-label={`主题：${label}，点击切换`}
    >
      <Icon />
    </button>
  )
}