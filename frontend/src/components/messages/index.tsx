import type { ChatMessage } from '../../lib/types'
import { MarkdownMessage } from './MarkdownMessage'
import { QuestionnaireCard } from './QuestionnaireCard'
import { QuestionnaireCompleteCard } from './QuestionnaireCompleteCard'
import { ResearchCard } from './ResearchCard'
import { SwotCard } from './SwotCard'

const registry: Record<string, React.ComponentType<any>> = {
  swot: SwotCard,
  research: ResearchCard,
  questionnaire: QuestionnaireCard,
  questionnaire_complete: QuestionnaireCompleteCard,
  markdown: MarkdownMessage,
  chat: MarkdownMessage,
}

export type MessageComponentProps = {
  message: ChatMessage
  sessionId?: string
  streaming?: boolean
  completed?: boolean
  onSubmitQuestionnaire?: (answers: any[]) => void
  onClarifyQuestion?: (keys: string[], prompt: string) => void
}

export function MessageContent(props: MessageComponentProps) {
  const Component = registry[props.message.type] ?? MarkdownMessage
  return <Component {...props} />
}
