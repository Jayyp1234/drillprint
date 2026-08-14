import { NavLink } from 'react-router-dom'
import { api } from '../lib/api'
import { useStreamStore } from '../store/streamStore'
import { useState } from 'react'

export function StageNav() {
  const connected = useStreamStore((s) => s.connected)
  const resetStream = useStreamStore((s) => s.resetStream)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const runReplay = async (cls: string) => {
    setBusy(true)
    setErr(null)
    resetStream()
    try {
      await api.replay(cls, 1042)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="stage-nav">
      <div className="brand">
        DRILLPRINT <span>instrument</span>
      </div>
      <nav className="nav-links" aria-label="Primary">
        <NavLink to="/" end>
          Monitor
        </NavLink>
        <NavLink to="/library">Library</NavLink>
        <NavLink to="/bench">Benchmark</NavLink>
        <NavLink to="/about">About</NavLink>
      </nav>
      <div className="nav-actions">
        <span className={`status-dot ${connected ? 'live' : ''}`} title={connected ? 'monitor live' : 'disconnected'} />
        <span className="num" style={{ color: 'var(--ink-dim)', fontSize: 11 }}>
          {connected ? 'LIVE' : 'OFF'}
        </span>
        <button className="btn" disabled={busy} onClick={() => runReplay('WHIRL_BACKWARD')}>
          Replay whirl
        </button>
        <button className="btn primary" disabled={busy} onClick={() => runReplay('STICK_SLIP')}>
          Replay stick-slip
        </button>
        {err && (
          <span className="num" style={{ color: 'var(--alert)', fontSize: 11 }} title={err}>
            ERR
          </span>
        )}
      </div>
    </header>
  )
}
