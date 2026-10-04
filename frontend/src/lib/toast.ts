import { useSyncExternalStore } from 'react'

export type ToastKind = 'info' | 'success' | 'error' | 'approval'

export interface Toast {
  id: number
  kind: ToastKind
  title: string
  body?: string
  href?: string
}

const LIFETIME_MS = 6_000
let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<() => void>()

function publish(next: Toast[]) {
  toasts = next
  listeners.forEach((listener) => listener())
}

export function toast(t: Omit<Toast, 'id'>) {
  const id = nextId++
  publish([...toasts, { ...t, id }].slice(-4))
  setTimeout(() => dismiss(id), LIFETIME_MS)
}

export function dismiss(id: number) {
  publish(toasts.filter((t) => t.id !== id))
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => toasts,
  )
}
