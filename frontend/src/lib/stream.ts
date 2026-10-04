// One shared EventSource for the whole app (pages never open their own connection).
// Keeps a bounded ring buffer of audit events and fans system events out to listeners.

import { useSyncExternalStore } from 'react'
import type { AuditEvent, EventPage, SystemEvent } from '../types/api'
import { API_URL, api } from './api'

export type StreamStatus = 'connecting' | 'live' | 'offline'

interface Snapshot {
  events: AuditEvent[] // newest first
  status: StreamStatus
}

const MAX_EVENTS = 500
const SILENCE_LIMIT_MS = 35_000 // the backend pings every 15 s

let snapshot: Snapshot = { events: [], status: 'connecting' }
let source: EventSource | null = null
let lastMessageAt = 0
const listeners = new Set<() => void>()
const systemListeners = new Set<(event: SystemEvent) => void>()

function publish(next: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...next }
  listeners.forEach((listener) => listener())
}

function merge(incoming: AuditEvent[]) {
  const byId = new Map(snapshot.events.map((e) => [e.id, e]))
  for (const event of incoming) byId.set(event.id, event)
  // ids are ULIDs: sorting them sorts by creation time
  const events = [...byId.values()].sort((a, b) => (a.id < b.id ? 1 : -1)).slice(0, MAX_EVENTS)
  publish({ events })
}

async function backfill() {
  try {
    const page = await api<EventPage>('/api/events?limit=200')
    merge(page.items)
  } catch {
    // offline: the live stream will fill in once the gateway is back
  }
}

function connect() {
  source?.close()
  publish({ status: 'connecting' })
  source = new EventSource(`${API_URL}/api/events/stream`)
  source.onopen = () => {
    lastMessageAt = Date.now()
    publish({ status: 'live' })
    void backfill()
  }
  source.onerror = () => publish({ status: 'offline' }) // EventSource retries by itself
  source.addEventListener('audit', (msg) => {
    lastMessageAt = Date.now()
    merge([JSON.parse((msg as MessageEvent<string>).data) as AuditEvent])
  })
  source.addEventListener('system', (msg) => {
    lastMessageAt = Date.now()
    const event = JSON.parse((msg as MessageEvent<string>).data) as SystemEvent
    systemListeners.forEach((listener) => listener(event))
  })
  source.addEventListener('ping', () => {
    lastMessageAt = Date.now()
  })
}

// A silently dead connection (laptop sleep, proxy timeout) never fires onerror: reconnect on silence.
setInterval(() => {
  if (source && snapshot.status === 'live' && Date.now() - lastMessageAt > SILENCE_LIMIT_MS) connect()
}, 5_000)

function subscribe(listener: () => void) {
  listeners.add(listener)
  if (!source) connect()
  return () => listeners.delete(listener)
}

export function useEventStream(): Snapshot {
  return useSyncExternalStore(subscribe, () => snapshot)
}

export function onSystemEvent(listener: (event: SystemEvent) => void): () => void {
  systemListeners.add(listener)
  if (!source) connect()
  return () => systemListeners.delete(listener)
}
