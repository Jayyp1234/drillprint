import { detectionCopy } from '../lib/format'
import { useStreamStore } from '../store/streamStore'

export function DetectionFeed() {
  const detections = useStreamStore((s) => s.detections)
  const selected = useStreamStore((s) => s.selected)
  const select = useStreamStore((s) => s.selectDetection)

  return (
    <aside className="panel detection-feed" aria-label="Detections">
      <div className="panel-title">Detection feed</div>
      <ul>
        {detections.length === 0 && (
          <li className="empty">No detections yet — run a replay or connect ingest.</li>
        )}
        {detections.map((d, i) => {
          const active = selected === d
          return (
            <li key={`${d.t}-${d.class}-${i}`}>
              <button
                type="button"
                className={`det tier-${d.tier} ${active ? 'active' : ''}`}
                onClick={() => select(d)}
              >
                <div className="det-head">
                  <span className={`pill t${d.tier}`}>{d.tier === 2 ? 'CONFIRMED' : 'ADVISORY'}</span>
                  <span className="num t">{d.t.toFixed(1)} s</span>
                </div>
                <div className="det-body">{detectionCopy(d)}</div>
              </button>
            </li>
          )
        })}
      </ul>
      <style>{`
        .detection-feed { display:flex; flex-direction:column; min-height:0; }
        .detection-feed ul { list-style:none; margin:0; padding:0; overflow:auto; flex:1; }
        .empty { padding:0.9rem; color:var(--ink-mute); font-size:12px; }
        .det {
          width:100%; text-align:left; border:0; border-bottom:1px solid var(--line);
          background:transparent; padding:0.7rem 0.75rem; color:var(--ink);
        }
        .det:hover { background: var(--bg-2); }
        .det.active { background: var(--bg-3); }
        .det-head { display:flex; justify-content:space-between; margin-bottom:0.3rem; }
        .pill {
          font-size:10px; font-weight:700; letter-spacing:0.08em;
          padding:0.12rem 0.35rem; border:1px solid;
        }
        .pill.t1 { color: var(--amber); border-color: var(--amber-dim); }
        .pill.t2 { color: var(--alert); border-color: var(--alert-dim); }
        .t { color: var(--ink-mute); font-size:11px; }
        .det-body { font-size:12px; line-height:1.35; color: var(--ink-dim); }
        .det.tier-2 .det-body { color: var(--ink); }
      `}</style>
    </aside>
  )
}
