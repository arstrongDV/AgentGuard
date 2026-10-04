export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString([], { hour12: false })
}

export function ms(value: number | null | undefined): string {
  if (value == null) return '–'
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`
  if (value >= 10) return `${value.toFixed(0)} ms`
  return `${value.toFixed(value < 1 ? 2 : 1)} ms`
}

export function usd(value: number | null | undefined): string {
  if (value == null) return '–'
  return value < 0.01 ? `$${value.toFixed(5)}` : `$${value.toFixed(2)}`
}

export function relative(iso: string, now = Date.now()): string {
  const seconds = Math.round((now - Date.parse(iso)) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}
