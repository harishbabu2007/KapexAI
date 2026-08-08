import type { ChatMessage } from '../../lib/types'
import { MarkdownMessage } from './MarkdownMessage'
import { QuestionnaireCard } from './QuestionnaireCard'
import { QuestionnaireCompleteCard } from './QuestionnaireCompleteCard'
import { ResearchCard } from './ResearchCard'
import { SwotCard } from './SwotCard'

interface MessageComponentProps {
  message: ChatMessage
}

export function MessageContent(props: MessageComponentProps) {
  const Component = registry[props.message.type] ?? MarkdownMessage
  return <Component {...props} />
}
