import type { ChatMessage, QuestionnaireAnswer } from '../../lib/types'

export interface MessageComponentProps {
  message: ChatMessage
  /** Active session the message belongs to (for tools that submit data back). */
  sessionId?: string
  /** True while a response is streaming — interactive cards should disable. */
  streaming?: boolean
  /** True when the message's flow already finished (e.g. questionnaire answered). */
  completed?: boolean
  /** Callback for tools that collect user input (e.g. the questionnaire). */
  onSubmitQuestionnaire?: (answers: QuestionnaireAnswer[]) => void
  /** Ask the worker to explain specific questionnaire questions in simpler words. */
  onClarifyQuestion?: (keys: string[], prompt: string) => void
}
