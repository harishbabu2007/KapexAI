import type {
  AuthenticatedUser,
  BusinessProfile,
  ChatMessage,
  FeedbackCategory,
  FeedbackDelivery,
  PendingMessage,
  QuestionnaireAnswer,
  SessionInfo,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  /**
   * The parsed error body, when the server returned JSON. Kept so callers can
   * read optional structured keys (`code`, `retry_after`, …) without changing
   * the human-readable `message` derived from `detail`.
   */
  body: unknown

  constructor(message: string, status: number, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST'
  body?: unknown
  token?: string | null
  /**
   * Lets the caller cancel an in-flight request. Used by the feedback dialog so
   * that closing it genuinely aborts the submission instead of leaving an
   * unstoppable write on the wire.
   */
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, token, signal } = options

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : undefined
    throw new ApiError(detail ?? `Request failed (${response.status})`, response.status, payload)
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
  /** True when the user has not saved any business profile fields yet. */
  profile_empty: boolean
  /**
   * Whether the feedback entry point should be shown. Optional so an older
   * backend that omits it is treated as "off" rather than crashing.
   */
  feedback_enabled?: boolean
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
  profile_empty: boolean
  feedback_enabled?: boolean
}

export type ProfileMe = AuthenticatedUser & {
  profile_empty: boolean
  feedback_enabled?: boolean
}

/** Fetches the current user from the backend; throws ApiError(401) when the token is invalid. */
export async function getMe(token: string): Promise<ProfileMe> {
  const me = await request<MeResponse>('/auth/me', { token })
  return {
    id: me.user_id,
    email: me.email,
    name: me.name,
    profile_empty: me.profile_empty,
    feedback_enabled: me.feedback_enabled ?? false,
  }
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

export function submitQuestionnaireAnswers(
  token: string,
  sessionId: string,
  answers: QuestionnaireAnswer[],
): Promise<{ session_id: string; job_id: string }> {
  return request<{ session_id: string; job_id: string }>(
    '/submit_questionnaire_answers',
    {
      method: 'POST',
      body: { session_id: sessionId, answers },
      token,
    },
  )
}

export function submitQuestionnaireClarification(
  token: string,
  sessionId: string,
  keys: string[],
): Promise<{ session_id: string; job_id: string }> {
  return request<{ session_id: string; job_id: string }>(
    '/submit_questionnaire_clarification',
    {
      method: 'POST',
      body: { session_id: sessionId, keys },
      token,
    },
  )
}

export function getMessages(
  token: string,
  sessionId: string,
): Promise<{ data: ChatMessage[]; pending: PendingMessage | null }> {
  return request<{ data: ChatMessage[]; pending: PendingMessage | null }>(
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

// ── Business Profile ─────────────────────────────────────────

export function getBusinessProfile(
  token: string,
): Promise<{ data: BusinessProfile }> {
  return request<{ data: BusinessProfile }>('/get_business_profile', { token })
}

export function updateBusinessProfile(
  token: string,
  profile: BusinessProfile,
): Promise<{ message: string; data: BusinessProfile }> {
  return request<{ message: string; data: BusinessProfile }>(
    '/update_business_profile',
    { method: 'POST', body: profile, token },
  )
}

// ── Feedback ─────────────────────────────────────────────────

export type FeedbackSubmission = {
  category: FeedbackCategory
  message: string
  contact_allowed: boolean
  /** Optional chat context; the backend verifies ownership. */
  session_id?: string | null
  /** Coerced server-side to a known app route. */
  page_path?: string | null
}

export type FeedbackSubmitResponse = {
  message: string
  feedback_id: string
  status: string
  delivery: FeedbackDelivery
}

export function submitFeedback(
  token: string,
  submission: FeedbackSubmission,
  signal?: AbortSignal,
): Promise<FeedbackSubmitResponse> {
  return request<FeedbackSubmitResponse>('/feedback', {
    method: 'POST',
    body: submission,
    token,
    signal,
  })
}

export type FeedbackFailure = {
  /** Safe, user-facing sentence from the backend (or a local fallback). */
  message: string
  /** Machine-readable backend code, e.g. `feedback_cooldown`. Null if absent. */
  code: string | null
  delivery: Exclude<FeedbackDelivery, 'delivered'>
  feedbackId: string | null
  retryAfterSeconds: number | null
}

/**
 * Normalizes a failed feedback submission into the fields the dialog needs.
 *
 * `delivery: 'uncertain'` is the important case: the request was sent but the
 * outcome was never confirmed, so the row may already be in the sheet and a
 * resubmission could duplicate it.
 */
export function describeFeedbackError(err: unknown): FeedbackFailure {
  const fallback: FeedbackFailure = {
    message: 'We could not send your feedback. Check your connection and try again.',
    code: null,
    delivery: 'failed',
    feedbackId: null,
    retryAfterSeconds: null,
  }
  if (!(err instanceof ApiError)) return fallback

  const body = (err.body ?? {}) as Record<string, unknown>
  const delivery = body.delivery === 'uncertain' ? 'uncertain' : 'failed'
  const code = typeof body.code === 'string' ? body.code : null
  const feedbackId = typeof body.feedback_id === 'string' ? body.feedback_id : null
  const retryAfter =
    typeof body.retry_after === 'number' && body.retry_after > 0
      ? body.retry_after
      : null

  return {
    message: err.message || fallback.message,
    code,
    delivery,
    feedbackId,
    retryAfterSeconds: retryAfter,
  }
}

// ── Waitlist ─────────────────────────────────────────────────

export function joinWaitlist(email: string, name?: string): Promise<{ message: string }> {
  return request<{ message: string }>('/waitlist', {
    method: 'POST',
    body: { email, name: name ?? null },
  })
}
