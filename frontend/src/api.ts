import type { Dashboard, ItemDetail } from './types'

/** An error returned by the API, using the same codes as the Python core. */
export class ApiError extends Error {
  readonly code: string
  readonly hint?: string
  readonly status: number

  constructor(code: string, message: string, status: number, hint?: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.hint = hint
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Could not reach the SpecHeap server.', 0, 'Is `specheap serve` running?')
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string; hint?: string } } | null)?.error
    throw new ApiError(
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? (response.statusText || `Request failed (${response.status})`),
      response.status,
      error?.hint,
    )
  }
  return body as T
}

let csrfToken: Promise<string> | null = null

function getCsrfToken(refresh = false): Promise<string> {
  if (refresh || csrfToken === null) {
    csrfToken = request<{ csrf_token: string }>('/api/session').then((s) => s.csrf_token)
  }
  return csrfToken
}

async function post<T>(path: string): Promise<T> {
  const send = async (refresh: boolean) =>
    request<T>(path, { method: 'POST', headers: { 'X-CSRF-Token': await getCsrfToken(refresh) } })
  try {
    return await send(false)
  } catch (error) {
    // The server may have restarted and issued a new token: retry once with a fresh one.
    if (error instanceof ApiError && error.code === 'CSRF_INVALID') return send(true)
    throw error
  }
}

export const api = {
  dashboard: () => request<Dashboard>('/api/dashboard'),
  item: (id: string) => request<ItemDetail>(`/api/items/${encodeURIComponent(id)}`),
  runAction: (id: string, action: string) =>
    post<ItemDetail>(`/api/items/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`),
}
