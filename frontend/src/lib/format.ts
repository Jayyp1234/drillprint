export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export function fmtP(p: number | null | undefined): string {
  if (p == null) return '—'
  if (p < 1e-4) return p.toExponential(0)
  return p.toFixed(4)
}

export function classLabel(cls: string): string {
  return cls.replaceAll('_', ' ')
}

export function detectionCopy(d: {
  class: string
  tier: number
  score: number
  p_corr: number
  confidence: number
  sssi?: number | null
  episode?: string
}): string {
  const verb = d.tier === 2 ? 'confirmed' : 'advisory'
  const ep = d.episode ? ` · ${d.episode.split('/').pop()}` : ''
  const sssi = d.sssi != null ? ` · SSSI ${d.sssi.toFixed(2)}` : ''
  return `${classLabel(d.class)} ${verb}${ep} · score ${d.score} · p ${fmtP(d.p_corr)}${sssi}`
}
