import { useEffect, useRef } from 'react'
import { api, wsMonitorUrl } from '../lib/api'
import type { MonitorMessage } from '../lib/types'
import { useStreamStore } from '../store/streamStore'

/** Open /ws/monitor and push the five message types into the store. */
export function useMonitorSocket(enabled = true) {
  const ingest = useStreamStore((s) => s.ingest)
  const setConnected = useStreamStore((s) => s.setConnected)
  const setChannels = useStreamStore((s) => s.setChannels)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false
    api.channels().then(setChannels).catch(() => undefined)

    if (!enabled) return

    let retry = 0
    let timer: number | undefined

    const connect = () => {
      if (cancelled) return
      const ws = new WebSocket(wsMonitorUrl())
      wsRef.current = ws
      ws.onopen = () => {
        retry = 0
        setConnected(true)
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as MonitorMessage
          ingest(msg)
        } catch {
          /* ignore malformed */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        const wait = Math.min(8000, 500 * 2 ** retry++)
        timer = window.setTimeout(connect, wait)
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      wsRef.current?.close()
    }
  }, [enabled, ingest, setChannels, setConnected])
}
