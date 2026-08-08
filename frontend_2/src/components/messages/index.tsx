import type { ChatMessage } from '../../lib/types'
import { MarkdownMessage } from './MarkdownMessage'
import { QuestionnaireCard } from './QuestionnaireCard'
import { QuestionnaireCompleteCard } from './QuestionnaireCompleteCard'
import { ResearchCard } from './ResearchCard'
import { SwotCard } from './SwotCard'

interface MessageComponentProps {
  message: ChatMessage
}

export function renderMessageCard(message: ChatMessage) {
  switch (message.type) {
    case 'swot':
      return <SwotCard message={message} />
    case 'research':
      return <ResearchCard message={message} />
    case 'questionnaire':
      return <QuestionnaireCard message={message} />
    case 'questionnaire_complete':
      return <QuestionnaireCompleteCard message={message} />
    case 'markdown':
    case 'chat':
    default:
      return <MarkdownMessage message={message} />
  }
}
