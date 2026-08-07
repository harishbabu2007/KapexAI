import type { AuthenticatedUser, ChatMessage, SessionInfo } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST'
  body?: unknown
  token?: string | null
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, token } = options

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : undefined
    throw new ApiError(detail ?? `Request failed (${response.status})`, response.status)
  }
  return payload as T
}

export function wsUrl(sessionId: string): string {
  return `${API_BASE_URL.replace(/^http/, 'ws')}/ws/session/${sessionId}`
}

// ── Auth ────────────────────────────────────────────────────

export type GoogleSignInResponse = {
  access_token: string
  user: AuthenticatedUser
}

export function signInWithGoogle(credential: string): Promise<GoogleSignInResponse> {
  return request<GoogleSignInResponse>('/auth/google', {
    method: 'POST',
    body: { credential },
  })
}

type MeResponse = {
  user_id: string
  email: string
  name: string | null
}

/** Fetches the current user from the backend; throws ApiError(401) when the token is invalid. */
export async function getMe(token: string): Promise<AuthenticatedUser> {
  const me = await request<MeResponse>('/auth/me', { token })
  return { id: me.user_id, email: me.email, name: me.name }
}

// ── Sessions ─────────────────────────────────────────────────

export function getSessions(token: string): Promise<{ data: SessionInfo[] }> {
  return request<{ data: SessionInfo[] }>('/get_sessions', { token })
}

export function createSession(
  token: string,
  content: string,
): Promise<{ session_id: string; job_id: string }> {
  return request<{ session_id: string; job_id: string }>('/create_chat_session', {
    method: 'POST',
    body: { content },
    token,
  })
}

export function pushMessage(
  token: string,
  sessionId: string,
  content: string,
): Promise<{ session_id: string; job_id: string }> {
  return request<{ session_id: string; job_id: string }>('/push_chat_message', {
    method: 'POST',
    body: { session_id: sessionId, content },
    token,
  })
}

export function getMessages(
  token: string,
  sessionId: string,
): Promise<{ data: ChatMessage[] }> {
  return request<{ data: ChatMessage[] }>(
    `/get_messages?session_id=${encodeURIComponent(sessionId)}`,
    { token },
  )
}

export function renameSession(
  token: string,
  sessionId: string,
  name: string,
): Promise<{ message: string; session_id: string; business_idea: string }> {
  return request<{ message: string; session_id: string; business_idea: string }>(
    '/rename_session',
    {
      method: 'POST',
      body: { session_id: sessionId, name },
      token,
    },
  )
}

export function deleteSession(
  token: string,
  sessionId: string,
): Promise<{ message: string; session_id: string }> {
  return request<{ message: string; session_id: string }>('/delete_session', {
    method: 'POST',
    body: { session_id: sessionId },
    token,
  })
}

// ── Waitlist ─────────────────────────────────────────────────

export function joinWaitlist(email: string, name?: string): Promise<{ message: string }> {
  return request<{ message: string }>('/waitlist', {
    method: 'POST',
    body: { email, name: name ?? null },
  })
}
