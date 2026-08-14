import { fmtNum } from '../lib/format'
import { useStreamStore } from '../store/streamStore'

export function RigStrip() {
  const twin = useStreamStore((s) => s.twin)
  const cells = [
    ['BIT', twin ? `${fmtNum(twin.bit_depth_m, 1)} m` : '—'],
    ['RPMₛ', twin ? fmtNum(twin.rpm_surface, 1) : '—'],
    ['RPMᵈʰ', twin ? fmtNum(twin.rpm_downhole, 1) : '—'],
    ['TQ', twin ? `${fmtNum(twin.torque_knm, 1)} kN·m` : '—'],
    ['WOB', twin ? `${fmtNum(twin.wob_kn, 0)} kN` : '—'],
    ['HKLD', twin ? `${fmtNum(twin.hookload_kn, 0)} kN` : '—'],
    ['TWIST', twin ? `${fmtNum(twin.twist_rad, 2)} rad` : '—'],
  ] as const

  const dets = twin?.active_detections ?? []
  const tier = dets.some((d) => d.tier === 2) ? 2 : dets.some((d) => d.tier === 1) ? 1 : 0

  return (
    <footer className={`rig-strip t${tier}`} aria-label="Rig context">
      {cells.map(([k, v]) => (
        <div key={k} className="cell">
          <span className="k">{k}</span>
          <span className="num v">{v}</span>
        </div>
      ))}
      <div className="cell scale">
        <span className="k">SCALE</span>
        <span className="num v">radial ×50 · mid-string compressed</span>
      </div>
      <style>{`
        .rig-strip {
          display:flex; gap:0; border-top:1px solid var(--line);
          background: rgba(7,13,11,0.95); min-height: var(--strip);
          align-items:stretch;
        }
        .rig-strip.t1 { box-shadow: inset 0 2px 0 var(--amber); }
        .rig-strip.t2 { box-shadow: inset 0 2px 0 var(--alert); }
        .cell {
          padding: 0.35rem 0.75rem; border-right:1px solid var(--line);
          display:flex; flex-direction:column; justify-content:center; min-width: 5.5rem;
        }
        .cell.scale { margin-left:auto; border-right:0; min-width: 14rem; }
        .k { font-size:9px; letter-spacing:0.1em; color:var(--ink-mute); }
        .v { font-size:12px; color:var(--phosphor); }
      `}</style>
    </footer>
  )
}
