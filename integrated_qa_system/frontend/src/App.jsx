import { Routes, Route } from 'react-router-dom'
import { useTheme } from './theme'
import Navbar from './components/Navbar'
import Workspace from './pages/Workspace'
import KbPage from './pages/KbPage'
import DocPage from './pages/DocPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  const { mode, theme, cycle } = useTheme()

  return (
    <div className="app">
      <Navbar mode={mode} cycle={cycle} />
      <Routes>
        <Route path="/" element={<Workspace />} />
        <Route path="/kb" element={<KbPage />} />
        <Route path="/kb/:docId" element={<DocPage />} />
        <Route path="/settings" element={<SettingsPage theme={theme} />} />
        <Route path="*" element={<Workspace />} />
      </Routes>
    </div>
  )
}