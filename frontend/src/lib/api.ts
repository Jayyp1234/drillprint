import type { ChannelBadge, LibraryInfo } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export function wsMonitorUrl(): string {
  if (BASE) {
    const u = new URL(BASE)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    u.pathname = '/ws/monitor'
    return u.toString()
  }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/monitor`
}

export const api = {
  health: () => getJson<{ ok: boolean; active_library: string | null }>('/health'),
  libraries: () => getJson<LibraryInfo[]>('/libraries'),
  channels: () => getJson<ChannelBadge[]>('/channels'),
  benchReport: () => getJson<Record<string, unknown>>('/bench/report'),
  activate: async (version: string) => {
    const res = await fetch(`${BASE}/libraries/${version}/activate`, { method: 'POST' })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  replay: async (className = 'WHIRL_BACKWARD', seed = 1042) => {
    const q = new URLSearchParams({ class_name: className, seed: String(seed) })
    const res = await fetch(`${BASE}/replay?${q}`, { method: 'POST' })
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<{
      ok: boolean
      detections: unknown[]
      n_messages: number
      n_twin: number
      duration_s: number
    }>
  },
}
