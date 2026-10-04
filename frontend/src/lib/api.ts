export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

const TOKEN_KEY = 'agentguard.adminToken'
const DEFAULT_ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN ?? 'dev-admin'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(typeof body === 'object' && body && 'detail' in body ? String(body.detail) : `HTTP ${status}`)
    this.status = status
    this.body = body
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 10_000)
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'content-type': 'application/json', ...init.headers },
    })
    const body: unknown = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text()
    if (!res.ok) throw new ApiError(res.status, body)
    return body as T
  } finally {
    clearTimeout(timer)
  }
}

export function getAdminToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? DEFAULT_ADMIN_TOKEN
  } catch {
    return DEFAULT_ADMIN_TOKEN
  }
}

export function setAdminToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // storage unavailable (private mode): the token lives for this page only
  }
}

export function adminHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getAdminToken()}` }
}
