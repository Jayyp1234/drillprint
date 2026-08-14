import { create } from 'zustand'
import type {
  ChannelBadge,
  ConstellationMsg,
  DetectionMsg,
  MonitorMessage,
  TwinStateMsg,
} from '../lib/types'

const MAX_DETECTIONS = 40
const MAX_SPEC_COLS = 240

export interface SpectralColumn {
  t: number
  bins: Uint8Array
  db_floor: number
  db_ceil: number
}

interface StreamState {
  connected: boolean
  twin: TwinStateMsg | null
  detections: DetectionMsg[]
  selected: DetectionMsg | null
  spectral: Record<string, SpectralColumn[]>
  constellation: ConstellationMsg | null
  caption: string | null
  channels: ChannelBadge[]
  focusChannel: string
  reducedMotion: boolean
  setConnected: (v: boolean) => void
  setChannels: (c: ChannelBadge[]) => void
  setFocusChannel: (c: string) => void
  selectDetection: (d: DetectionMsg | null) => void
  resetStream: () => void
  ingest: (msg: MonitorMessage) => void
}

const emptyTwin = null

export const useStreamStore = create<StreamState>((set, get) => ({
  connected: false,
  twin: emptyTwin,
  detections: [],
  selected: null,
  spectral: {},
  constellation: null,
  caption: null,
  channels: [],
  focusChannel: 'ACC_LAT_X',
  reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  setConnected: (connected) => set({ connected }),
  setChannels: (channels) => set({ channels }),
  setFocusChannel: (focusChannel) => set({ focusChannel }),
  selectDetection: (selected) => set({ selected }),
  resetStream: () =>
    set({
      twin: null,
      detections: [],
      selected: null,
      spectral: {},
      constellation: null,
      caption: null,
    }),
  ingest: (msg) => {
    switch (msg.type) {
      case 'twin_state':
        set({ twin: msg })
        break
      case 'detection': {
        const detections = [msg, ...get().detections].slice(0, MAX_DETECTIONS)
        const selected = get().selected ?? (msg.tier === 2 ? msg : get().selected)
        set({ detections, selected: msg.tier === 2 ? msg : selected })
        break
      }
      case 'spectral_frame': {
        const key = `${msg.channel}:${msg.profile}`
        const bins = b64ToU8(msg.data_b64)
        const col: SpectralColumn = {
          t: msg.t,
          bins,
          db_floor: msg.db_floor,
          db_ceil: msg.db_ceil,
        }
        const prev = get().spectral[key] ?? []
        const next = [...prev, col].slice(-MAX_SPEC_COLS)
        set({ spectral: { ...get().spectral, [key]: next } })
        break
      }
      case 'constellation':
        set({ constellation: msg })
        break
      case 'scenario_event':
        set({ caption: (msg.caption as string) ?? null })
        break
      default:
        break
    }
  },
}))

function b64ToU8(b64: string): Uint8Array {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function pickSpectral(
  spectral: Record<string, SpectralColumn[]>,
  channel: string,
): SpectralColumn[] {
  const keys = Object.keys(spectral).filter((k) => k.startsWith(`${channel}:`))
  if (!keys.length) return []
  // Prefer HIGH / ORDER display profiles when present
  const prefer = keys.find((k) => /HIGH|ORDER|MID|LOW_DECIM|LOW/.test(k)) ?? keys[0]
  return spectral[prefer] ?? []
}
