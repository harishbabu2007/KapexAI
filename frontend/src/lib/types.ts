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

/** A single regulatory/legal item found by `indian_legal_search`. */
export type LegalResearchResult = {
  title: string | null
  source_url: string | null
  authority: string | null
  official_source: boolean
  source_type: 'official' | 'third_party'
  document_type: string | null
  jurisdiction: string | null
  publication_date: string | null
  effective_date: string | null
  relevant_sections: string[]
  citation: string | null
  summary: string | null
}

/** A single judgment found by `indian_case_search` (via Indian Kanoon). */
export type IndianCase = {
  case_name: string | null
  court: string | null
  citation: string | null
  date: string | null
  summary: string | null
  relevance: string | null
  url: string | null
  source_label: string | null
  source_type: string | null
}

/** A single prioritized compliance issue from `legal_issue_register`. */
export type LegalIssue = {
  title: string
  category: string | null
  basis: 'source' | 'user_concern' | 'inference'
  grounded_in: string[]
  explanation: string
  mitigation: string | null
  likelihood: number
  severity: number
  urgency: number
  priority_score: number
  priority: 'critical' | 'high' | 'medium' | 'low'
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
  | {
      type: 'legal_research'
      content: string
      query: string
      results: LegalResearchResult[]
      disclaimer: string
    }
  | {
      type: 'case_search'
      content: string
      query: string
      cases: IndianCase[]
      disclaimer: string
    }
  | {
      type: 'issue_register'
      content: string
      issues: LegalIssue[]
      disclaimer: string
      type: 'indian_finance'
      content: string
      calculation_type: string
      result: Record<string, unknown>
    }
  | { type: 'suggestions'; tools: ToolInfo[] }
  | { type: 'end' }
  | { type: 'error'; job_id: string; content: string }
