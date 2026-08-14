import { useStreamStore } from '../store/streamStore'

export function ChannelRail() {
  const channels = useStreamStore((s) => s.channels)
  const focus = useStreamStore((s) => s.focusChannel)
  const setFocus = useStreamStore((s) => s.setFocusChannel)
  const twin = useStreamStore((s) => s.twin)

  const spark = (name: string): number => {
    if (!twin) return 0
    switch (name) {
      case 'TORQUE_SURF':
        return twin.torque_knm
      case 'RPM_SURF':
        return twin.rpm_surface
      case 'RPM_DH':
        return twin.rpm_downhole
      case 'WOB':
        return twin.wob_kn
      case 'HOOKLOAD':
        return twin.hookload_kn
      default:
        return 0
    }
  }

  return (
    <aside className="panel channel-rail" aria-label="Channels">
      <div className="panel-title">Channels</div>
      <ul>
        {(channels.length
          ? channels
          : [
              { channel: 'TORQUE_SURF', fs: 10, observes: ['STICK_SLIP'], badge: null },
              { channel: 'RPM_SURF', fs: 10, observes: [], badge: null },
              { channel: 'ACC_LAT_X', fs: 400, observes: ['WHIRL_BACKWARD'], badge: null },
              { channel: 'ACC_AX', fs: 100, observes: ['BIT_BOUNCE'], badge: null },
              { channel: 'WOB', fs: 10, observes: ['BIT_BOUNCE'], badge: 'partial band — not matchable' },
            ]
        ).map((c) => {
          const active = c.channel === focus
          const blind = c.entirely_blind || (c.observes.length === 0 && c.badge == null && !['RPM_SURF', 'HOOKLOAD', 'BIT_DEPTH', 'HOLE_DEPTH', 'BLOCK_POS'].includes(c.channel))
          return (
            <li key={c.channel}>
              <button
                type="button"
                className={`ch ${active ? 'active' : ''} ${blind ? 'blind' : ''}`}
                onClick={() => setFocus(c.channel)}
              >
                <div className="ch-top">
                  <span className="ch-name">{c.channel}</span>
                  <span className="num ch-fs">{c.fs ?? '—'} Hz</span>
                </div>
                <div className="ch-spark num">{spark(c.channel).toFixed(1)}</div>
                <div className="ch-badges">
                  {c.observes.map((o) => (
                    <span key={o} className="badge ok">
                      {o.replace('WHIRL_BACKWARD', 'WHIRL').replace('STICK_SLIP', 'SS').replace('BIT_BOUNCE', 'BNC')}
                    </span>
                  ))}
                  {c.badge && <span className="badge warn">{c.badge}</span>}
                  {blind && <span className="badge mute">entirely blind</span>}
                </div>
              </button>
            </li>
          )
        })}
      </ul>
      <style>{`
        .channel-rail { display:flex; flex-direction:column; min-height:0; overflow:hidden; }
        .channel-rail ul { list-style:none; margin:0; padding:0; overflow:auto; flex:1; }
        .ch {
          width:100%; text-align:left; border:0; border-bottom:1px solid var(--line);
          background:transparent; padding:0.65rem 0.75rem; color:var(--ink);
        }
        .ch:hover { background: var(--bg-2); }
        .ch.active { background: var(--bg-3); box-shadow: inset 3px 0 0 var(--phosphor); }
        .ch.blind .ch-name { color: var(--ink-mute); }
        .ch-top { display:flex; justify-content:space-between; gap:0.5rem; }
        .ch-name { font-family: var(--font-mono); font-size:12px; font-weight:500; }
        .ch-fs { color: var(--ink-mute); font-size:11px; }
        .ch-spark { color: var(--phosphor); font-size:13px; margin:0.2rem 0; }
        .ch-badges { display:flex; flex-wrap:wrap; gap:0.25rem; }
        .badge {
          font-size:9px; letter-spacing:0.06em; text-transform:uppercase;
          padding:0.1rem 0.3rem; border:1px solid var(--line-strong); color:var(--ink-dim);
        }
        .badge.ok { border-color: var(--phosphor-dim); color: var(--phosphor); }
        .badge.warn { border-color: var(--amber-dim); color: var(--amber); }
        .badge.mute { color: var(--ink-mute); }
      `}</style>
    </aside>
  )
}
