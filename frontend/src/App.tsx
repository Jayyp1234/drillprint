import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { StageNav } from './components/StageNav'
import { useMonitorSocket } from './hooks/useMonitorSocket'
import { AboutScreen } from './screens/AboutScreen'
import { BenchmarkScreen } from './screens/BenchmarkScreen'
import { LibraryScreen } from './screens/LibraryScreen'
import { MonitorScreen } from './screens/MonitorScreen'
import './styles/global.css'

export default function App() {
  useMonitorSocket(true)
  return (
    <BrowserRouter>
      <div className="app-shell">
        <StageNav />
        <Routes>
          <Route path="/" element={<MonitorScreen />} />
          <Route path="/library" element={<LibraryScreen />} />
          <Route path="/bench" element={<BenchmarkScreen />} />
          <Route path="/about" element={<AboutScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
