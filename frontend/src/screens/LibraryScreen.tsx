import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { LibraryInfo } from '../lib/types'

export function LibraryScreen() {
  const [libs, setLibs] = useState<LibraryInfo[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = () =>
    api
      .libraries()
      .then(setLibs)
      .catch((e) => setErr(String(e)))

  useEffect(() => {
    load()
  }, [])

  const activate = async (v: string) => {
    setBusy(v)
    setErr(null)
    try {
      await api.activate(v)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="screen library">
      <div className="panel" style={{ margin: '0.75rem', overflow: 'auto' }}>
        <div className="panel-title">Fingerprint libraries</div>
        {err && <div className="empty-state" style={{ color: 'var(--alert)' }}>{err}</div>}
        {!libs.length && !err && (
          <div className="empty-state">
            Build the fingerprint library to begin —{' '}
            <code>drillprint library build --config well01.yaml</code>
          </div>
        )}
        <table className="lib-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Status</th>
              <th>Episodes</th>
              <th>Hashes</th>
              <th>Approved</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {libs.map((l) => (
              <tr key={l.version} className={l.active ? 'active' : ''}>
                <td className="num">{l.version}</td>
                <td>{l.status}</td>
                <td className="num">
                  {l.episodes_by_class
                    ? Object.entries(l.episodes_by_class)
                        .map(([k, n]) => `${k.split('_')[0]} ${n}`)
                        .join(' · ')
                    : '—'}
                </td>
                <td className="num">{l.n_hashes?.toLocaleString() ?? '—'}</td>
                <td className="num">{l.approved_by ?? '—'}</td>
                <td>
                  {l.active ? (
                    <span className="tier-1">ACTIVE</span>
                  ) : (
                    <button
                      className="btn"
                      disabled={l.status !== 'approved' || busy === l.version}
                      onClick={() => activate(l.version)}
                      title={l.status !== 'approved' ? 'Only approved libraries can activate' : ''}
                    >
                      Activate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <style>{`
        .lib-table { width:100%; border-collapse:collapse; font-size:13px; }
        .lib-table th, .lib-table td {
          text-align:left; padding:0.65rem 0.75rem; border-bottom:1px solid var(--line);
        }
        .lib-table th {
          color:var(--ink-mute); font-size:11px; letter-spacing:0.08em; text-transform:uppercase;
        }
        .lib-table tr.active { background: var(--bg-3); }
      `}</style>
    </div>
  )
}
