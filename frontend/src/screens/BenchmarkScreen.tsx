import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export function BenchmarkScreen() {
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api
      .benchReport()
      .then(setReport)
      .catch((e) => setErr(String(e)))
  }, [])

  if (err) {
    return <div className="empty-state">Failed to load report: {err}</div>
  }
  if (!report) {
    return <div className="empty-state">Loading bench/report.json…</div>
  }
  if (report.status === 'missing') {
    return (
      <div className="empty-state">
        No benchmark report yet. Run <code>python -m bench.run --smoke</code> (or{' '}
        <code>drillprint bench run</code>).
      </div>
    )
  }

  const cal = report.calibration as {
    baseline?: { thresholds?: Record<string, number>; budget_fa_per_hour?: number }
    tier1?: { thresholds?: Record<string, number>; budget_fa_per_hour?: number }
  }
  const results = report.results as Record<
    string,
    {
      drillprint?: Record<string, Record<string, number>>
      baseline?: Record<string, Record<string, number>>
      data_hours?: number
    }
  >

  return (
    <div className="screen bench">
      <div className="panel" style={{ margin: '0.75rem', overflow: 'auto' }}>
        <div className="panel-title">
          Benchmark · {String(report.protocol)} · lib {String(report.library_version)}
        </div>
        <div className="grid">
          <section>
            <h3>Calibration</h3>
            <p className="num">
              Baseline FA budget {cal?.baseline?.budget_fa_per_hour ?? '—'}/h · Tier-1{' '}
              {cal?.tier1?.budget_fa_per_hour ?? '—'}/h
            </p>
            <table>
              <thead>
                <tr>
                  <th>Class</th>
                  <th>Baseline thr</th>
                  <th>Tier-1 thr</th>
                </tr>
              </thead>
              <tbody>
                {['STICK_SLIP', 'WHIRL_BACKWARD', 'BIT_BOUNCE'].map((c) => (
                  <tr key={c}>
                    <td>{c}</td>
                    <td className="num">{fmt(cal?.baseline?.thresholds?.[c])}</td>
                    <td className="num">{fmt(cal?.tier1?.thresholds?.[c])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section>
            <h3>T_tol (A19)</h3>
            <pre className="num">{JSON.stringify(report.t_tol, null, 2)}</pre>
          </section>
        </div>
        {Object.entries(results ?? {}).map(([snr, block]) => (
          <section key={snr} style={{ marginTop: '1rem' }}>
            <h3>SNR {snr} dB · {block.data_hours?.toFixed?.(3) ?? '—'} data-hours</h3>
            <table>
              <thead>
                <tr>
                  <th>Class</th>
                  <th>DP F1</th>
                  <th>DP P/R</th>
                  <th>TP/FP/FN/late</th>
                  <th>Baseline F1</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys({ ...block.drillprint, ...block.baseline }).map((cls) => {
                  const d = block.drillprint?.[cls]
                  const b = block.baseline?.[cls]
                  return (
                    <tr key={cls}>
                      <td>{cls}</td>
                      <td className="num">{fmt(d?.f1)}</td>
                      <td className="num">
                        {fmt(d?.precision)} / {fmt(d?.recall)}
                      </td>
                      <td className="num">
                        {d ? `${d.tp}/${d.fp}/${d.fn}/${d.late}` : '—'}
                      </td>
                      <td className="num">{fmt(b?.f1)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>
        ))}
      </div>
      <style>{`
        .bench h3 {
          margin: 0.75rem 0.75rem 0.35rem;
          font-size: 12px;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--ink-mute);
          font-weight: 600;
        }
        .bench .grid {
          display: grid;
          grid-template-columns: 1.4fr 1fr;
          gap: 1rem;
        }
        .bench table {
          width: calc(100% - 1.5rem);
          margin: 0 0.75rem 0.75rem;
          border-collapse: collapse;
          font-size: 13px;
        }
        .bench th, .bench td {
          text-align: left;
          padding: 0.45rem 0.5rem;
          border-bottom: 1px solid var(--line);
        }
        .bench th {
          color: var(--ink-mute);
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }
        .bench pre {
          margin: 0 0.75rem;
          color: var(--phosphor);
          font-size: 12px;
        }
        .bench p { margin: 0 0.75rem 0.5rem; color: var(--ink-dim); }
        @media (max-width: 900px) {
          .bench .grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}

function fmt(n?: number) {
  return n == null ? '—' : n.toFixed(3)
}
