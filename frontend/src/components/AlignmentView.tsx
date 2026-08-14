import { useEffect, useRef } from 'react'
import { detectionCopy, fmtP } from '../lib/format'
import type { DetectionMsg } from '../lib/types'
import { useStreamStore } from '../store/streamStore'

/** Signature Alignment View — offset histogram spike (§19). */
export function AlignmentView({ detection }: { detection: DetectionMsg | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reduced = useStreamStore((s) => s.reducedMotion)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !detection?.histogram) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const cssW = canvas.clientWidth
    const cssH = canvas.clientHeight
    canvas.width = Math.floor(cssW * dpr)
    canvas.height = Math.floor(cssH * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const entries = Object.entries(detection.histogram)
      .map(([k, v]) => [Number(k), v] as const)
      .sort((a, b) => a[0] - b[0])
    if (!entries.length) return

    const max = Math.max(...entries.map((e) => e[1]), 1)
    const pad = 28
    const w = cssW - pad * 2
    const h = cssH - pad * 2
    const barW = Math.max(2, w / entries.length - 1)

    ctx.fillStyle = '#070d0b'
    ctx.fillRect(0, 0, cssW, cssH)

    // Poisson noise floor line at λ
    const lam = detection.lambda ?? 0.05
    const yLam = pad + h - (Math.min(lam, max) / max) * h
    ctx.strokeStyle = 'rgba(138,163,148,0.5)'
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(pad, yLam)
    ctx.lineTo(cssW - pad, yLam)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = '#8aa394'
    ctx.font = '11px "IBM Plex Mono"'
    ctx.fillText(`λ ≈ ${lam.toFixed(3)}`, pad, yLam - 6)

    const star = detection.delta_star
    entries.forEach(([bin, count], i) => {
      const x = pad + (i / entries.length) * w
      const bh = (count / max) * h
      const isStar = star != null && bin === star
      ctx.fillStyle = isStar ? '#e6322a' : '#2a9a55'
      if (reduced || !isStar) {
        ctx.fillRect(x, pad + h - bh, barW, bh)
      } else {
        // spike rises — one intentional motion
        const frames = 24
        let f = 0
        const animate = () => {
          f++
          const k = Math.min(1, f / frames)
          const ease = 1 - (1 - k) ** 3
          ctx.fillStyle = '#070d0b'
          ctx.fillRect(x - 1, pad, barW + 2, h)
          ctx.fillStyle = '#e6322a'
          ctx.fillRect(x, pad + h - bh * ease, barW, bh * ease)
          if (k < 1) requestAnimationFrame(animate)
        }
        animate()
      }
    })

    ctx.fillStyle = '#5c7366'
    ctx.font = '11px "IBM Plex Mono"'
    ctx.fillText('δ bin', pad, cssH - 8)
    ctx.fillText('count', 8, pad + 8)
  }, [detection, reduced])

  if (!detection) {
    return (
      <div className="panel align empty-wrap">
        <div className="panel-title">Alignment View</div>
        <div className="empty-state">
          Select a detection to see the offset histogram — the proof spike beside the Poisson floor.
        </div>
      </div>
    )
  }

  return (
    <div className="panel align">
      <div className="panel-title">Alignment View · audit</div>
      <div className="align-meta">
        <div>{detectionCopy(detection)}</div>
        <div className="num meta-row">
          confidence {detection.confidence.toFixed(4)} · p_corr {fmtP(detection.p_corr)}
          {detection.p_geom_corr != null && ` · p_geom ${fmtP(detection.p_geom_corr)}`}
          {detection.library_version && ` · lib ${detection.library_version}`}
        </div>
      </div>
      <div className="align-canvas">
        {detection.histogram && Object.keys(detection.histogram).length > 0 ? (
          <canvas ref={canvasRef} />
        ) : (
          <div className="empty-state">
            Geometry match (flat offset histogram) — distinct types{' '}
            <span className="num">{detection.distinct_matched ?? '—'}</span>. The Alignment spike
            appears for evolving/transient content; steady-state cross-realization detections
            lead with matched-type overlap (E4).
          </div>
        )}
      </div>
      <style>{`
        .align { display:flex; flex-direction:column; min-height:0; height:100%; }
        .align-meta { padding:0.65rem 0.75rem; border-bottom:1px solid var(--line); font-size:12px; }
        .meta-row { color:var(--ink-mute); margin-top:0.25rem; font-size:11px; }
        .align-canvas { flex:1; min-height:180px; position:relative; }
        .align-canvas canvas { width:100%; height:100%; display:block; }
        .empty-wrap .empty-state { padding:1rem 0.75rem; }
      `}</style>
    </div>
  )
}
