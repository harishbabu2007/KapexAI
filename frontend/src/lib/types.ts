export type AuthenticatedUser = {
  id: string
  email: string
  name: string | null
}

/**
 * The user's saved business profile. Every key is optional — a blank (or all
 * empty) profile means the worker treats the user as having no head-start
 * context. The `content` column of the `BusinessProfile` table stores exactly
 * these keys.
 */
export type BusinessProfile = {
  your_name?: string
  industry?: string
  about_you?: string
  business_history?: string
  location?: string
  monthly_income?: string
  monthly_expenditure?: string
}

export type SessionInfo = {
  id: string
  business_idea: string
  status: string
  created_at: string
}

export type QuestionnaireQuestion = {
  key: string
  question: string
}

export type QuestionnaireAnswer = {
  key: string
  answer: string
}

export type SwotSections = {
  strengths: string[]
  weaknesses: string[]
  opportunities: string[]
  threats: string[]
}

/**
 * A single entry in a session's message log.
 *
 * `type` is the discriminator for the message and selects which component the
 * frontend renders (see `components/messages`). Extra fields are tool-specific
 * and carried through `[key: string]: unknown`.
 */
export type ChatMessage = {
  id?: string
  role: 'USER' | 'ASSISTANT'
  agent?: string
  type: string
  content: string
  created_at?: string
  // True for the optimistic echo of an in-flight message loaded from another tab.
  pending?: boolean
  [key: string]: unknown
}

/** A user message the worker has not finished replying to yet. */
export type PendingMessage = {
  content: string
  type: string
}

export type ToolInfo = {
  name: string
  description: string
  example: string
  suggestion: string
}

/**
 * Frames published by the worker to `stream:{session_id}` and forwarded
 * verbatim by the backend WebSocket (`/ws/session/{session_id}`).
 */
export type StreamFrame =
  | { type: 'chat'; content: string }
  | {
      type: 'questionnaire'
      content: string
      questions: QuestionnaireQuestion[]
      facts: Record<string, string>
    }
  | { type: 'questionnaire_complete'; content: string; context: Record<string, string> }
  | { type: 'swot'; content: string; sections: SwotSections; summary?: string }
  | { type: 'research'; content: string }
  | { type: 'astrology'; content: string; insights: string[]; disclaimer: string }
  | { type: 'suggestions'; tools: ToolInfo[] }
  | { type: 'end' }
  | { type: 'error'; job_id: string; content: string }
