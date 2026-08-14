export function AboutScreen() {
  return (
    <div className="screen about">
      <div className="about-inner">
        <h1>DRILLPRINT</h1>
        <p className="lede">
          Training-free, physics-derived spectral fingerprinting for real-time drilling
          dysfunction recognition — retrieval with per-alert proof, not a black-box classifier.
        </p>
        <div className="eqs">
          <article>
            <h2>STFT</h2>
            <pre className="num">{`S[m, k] = |Σ x[n] w[n−mH] e^{−j2πkn/N}|`}</pre>
            <p>Per-profile Hann frames. LOW / ORDER hashed; MID / HIGH display.</p>
          </article>
          <article>
            <h2>Hash tuple</h2>
            <pre className="num">{`(f₁, Δk, Δt) → 10|8|6 = 24-bit`}</pre>
            <p>Combinatorial landmarks; library and query share T_max by profile.</p>
          </article>
          <article>
            <h2>Whirl orbit</h2>
            <pre className="num">{`Ω_orbit = −N_b · ω`}</pre>
            <p>
              Inertial BHA orbit (twin). Fingerprints hash the sensor-frame line at order N_b+1.
            </p>
          </article>
        </div>
        <p className="foot">
          Amber = Tier-1 advisory · Red = Tier-2 confirmed exclusively. Alignment View is the proof.
        </p>
      </div>
      <style>{`
        .about-inner {
          max-width: 920px;
          margin: 0 auto;
          padding: 2.5rem 1.25rem 3rem;
        }
        .about h1 {
          font-family: var(--font-mono);
          letter-spacing: 0.18em;
          color: var(--phosphor);
          font-size: 1.6rem;
          margin: 0 0 0.75rem;
        }
        .lede {
          color: var(--ink-dim);
          font-size: 1.05rem;
          line-height: 1.5;
          max-width: 40rem;
        }
        .eqs {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 0.75rem;
          margin-top: 2rem;
        }
        .eqs article {
          border: 1px solid var(--line);
          background: rgba(11,21,18,0.9);
          padding: 1rem;
        }
        .eqs h2 {
          margin: 0 0 0.5rem;
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--ink-mute);
        }
        .eqs pre {
          margin: 0 0 0.6rem;
          color: var(--phosphor);
          white-space: pre-wrap;
          font-size: 12px;
        }
        .eqs p { margin: 0; color: var(--ink-dim); font-size: 13px; line-height: 1.4; }
        .foot {
          margin-top: 2rem;
          color: var(--ink-mute);
          font-size: 12px;
          letter-spacing: 0.04em;
        }
        @media (max-width: 800px) {
          .eqs { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
