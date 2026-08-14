import { useEffect, useRef } from 'react'
import { pickSpectral, useStreamStore } from '../store/streamStore'

/** Scrolling spectrogram from spectral_frame uint8 columns (§17). */
export function Spectrogram() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const focus = useStreamStore((s) => s.focusChannel)
  const spectral = useStreamStore((s) => s.spectral)
  const constellation = useStreamStore((s) => s.constellation)
  const cols = pickSpectral(spectral, focus)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const parent = canvas.parentElement
    if (!parent) return
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.floor(parent.clientWidth * dpr)
      canvas.height = Math.floor(parent.clientHeight * dpr)
      canvas.style.width = `${parent.clientWidth}px`
      canvas.style.height = `${parent.clientHeight}px`
      draw()
    }
    const draw = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const w = canvas.width
      const h = canvas.height
      ctx.fillStyle = '#070d0b'
      ctx.fillRect(0, 0, w, h)

      if (!cols.length) {
        ctx.fillStyle = '#5c7366'
        ctx.font = `${12 * (window.devicePixelRatio || 1)}px "IBM Plex Mono"`
        ctx.fillText('awaiting spectral_frame…', 16, 28)
        return
      }

      const nCols = cols.length
      const nBins = cols[0].bins.length
      const colW = w / Math.max(nCols, 1)
      for (let i = 0; i < nCols; i++) {
        const col = cols[i]
        for (let b = 0; b < nBins; b++) {
          const v = col.bins[b] / 255
          const y0 = h - ((b + 1) / nBins) * h
          const y1 = h - (b / nBins) * h
          ctx.fillStyle = phosphorColor(v)
          ctx.fillRect(i * colW, y0, Math.ceil(colW) + 0.5, Math.max(1, y1 - y0))
        }
      }

      // predicted f0 band marker for torque (stick-slip prior)
      if (focus === 'TORQUE_SURF' || focus === 'RPM_DH') {
        const f0 = 0.25 // ~T_model prior at reference well; HUD states the band
        const fMax = 5 // LOW Nyquist display proxy for 10 Hz
        const y = h - (f0 / fMax) * h
        const yLo = h - (f0 / 2 / fMax) * h
        ctx.fillStyle = 'rgba(232,163,23,0.12)'
        ctx.fillRect(0, y, w, yLo - y)
        ctx.strokeStyle = 'rgba(232,163,23,0.7)'
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(w, y)
        ctx.stroke()
      }

      if (constellation && constellation.channel === focus) {
        ctx.fillStyle = '#e6322a'
        for (const p of constellation.peaks.slice(0, 40)) {
          const x = w - colW * 2
          const y = h - (p.bin / Math.max(nBins - 1, 1)) * h
          ctx.fillRect(x - 2, y - 2, 4, 4)
        }
      }
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(parent)
    return () => ro.disconnect()
  }, [cols, constellation, focus])

  return (
    <div className="panel spectrogram">
      <div className="panel-title">
        Spectrogram · <span className="num">{focus}</span>
        <span style={{ float: 'right', color: 'var(--ink-mute)' }}>
          {cols.length ? `${cols.length} frames` : 'idle'}
        </span>
      </div>
      <div className="spec-body">
        <canvas ref={canvasRef} />
      </div>
      <style>{`
        .spectrogram { display:flex; flex-direction:column; min-height:0; height:100%; }
        .spec-body { flex:1; min-height:0; position:relative; }
        .spec-body canvas { display:block; width:100%; height:100%; }
      `}</style>
    </div>
  )
}

function phosphorColor(v: number): string {
  // dark → phosphor green
  const g = Math.floor(20 + v * 220)
  const r = Math.floor(8 + v * 40)
  const b = Math.floor(12 + v * 80)
  return `rgb(${r},${g},${b})`
}
