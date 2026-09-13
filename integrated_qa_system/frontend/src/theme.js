import { useEffect, useState, useCallback } from 'react'

// 主题只存三个状态：'light' | 'dark' | 'auto'（跟随系统）
// 应用到 <html data-theme> 上，所有样式走 CSS 变量，App.css 里定义两套。
const KEY = 'rag_theme'

function resolveTheme(mode, systemDark) {
  if (mode === 'auto') return systemDark ? 'dark' : 'light'
  return mode
}

export function useTheme() {
  // 初始：localStorage 里存的是 'light' | 'dark' | 'auto'，缺省 auto
  const [mode, setMode] = useState(() => localStorage.getItem(KEY) || 'auto')
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches,
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => setSystemDark(e.matches)
    if (mq.addEventListener) mq.addEventListener('change', handler)
    else mq.addListener(handler)
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', handler)
      else mq.removeListener(handler)
    }
  }, [])

  const theme = resolveTheme(mode, systemDark)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(KEY, mode)
  }, [theme, mode])

  const cycle = useCallback(() => {
    // 顺序：auto → light → dark → auto
    setMode((m) => (m === 'auto' ? 'light' : m === 'light' ? 'dark' : 'auto'))
  }, [])

  return { mode, theme, cycle, setMode }
}