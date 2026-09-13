import { createContext, useContext, useCallback, useMemo, useRef, useState } from 'react'

// 全局 Toast：统一错误/成功反馈，替换各页面零散 setXxxMsg。
// 用法：const toast = useToast()；toast.error('xx') / toast.success('yy') / toast.info('zz')。
// toast 自动 3.2s 消失，可传第二个参数覆盖时长（ms）。

const ToastContext = createContext(null)
export const useToast = () => useContext(ToastContext)

let uid = 0
const nextId = () => `toast_${++uid}`

export default function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((prev) => {
      const t = prev.find((x) => x.id === id)
      if (!t) return prev
      // 标记 leaving，动画结束后再移除，避免闪烁
      if (!t.leaving) {
        clearTimeout(timers.current.get(id))
        const leaveTimer = setTimeout(() => {
          setToasts((cur) => cur.filter((x) => x.id !== id))
          timers.current.delete(id)
        }, 200)
        timers.current.set(id, leaveTimer)
        return prev.map((x) => (x.id === id ? { ...x, leaving: true } : x))
      }
      return prev
    })
  }, [])

  const push = useCallback(
    (type, message, duration = 3200) => {
      const id = nextId()
      setToasts((prev) => [...prev, { id, type, message }])
      const t = setTimeout(() => dismiss(id), duration)
      timers.current.set(id, t)
      // 同一时刻只保留最多 3 条，避免堆叠遮挡
      setToasts((prev) => (prev.length > 3 ? prev.slice(-3) : prev))
    },
    [dismiss],
  )

  const api = useMemo(
    () => ({
      success: (m, d) => push('success', m, d),
      error: (m, d) => push('error', m, d),
      info: (m, d) => push('info', m, d),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-container" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}${t.leaving ? ' leaving' : ''}`} onClick={() => dismiss(t.id)}>
            <span className="toast-dot" />
            <span className="toast-msg">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}