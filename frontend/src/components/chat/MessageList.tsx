import type { ChatMessage, QuestionnaireAnswer } from '../../lib/types'
import { MessageContent } from '../messages'

type MessageListProps = {
  messages: ChatMessage[]
  sessionId?: string
  streaming?: boolean
  onSubmitQuestionnaire?: (answers: QuestionnaireAnswer[]) => void
  onClarifyQuestion?: (keys: string[], prompt: string) => void
}

type MessageItemProps = MessageListProps & {
  message: ChatMessage
  index: number
}
function MessageItem({
  message,
  messages,
  index,
  sessionId,
  streaming,
  onSubmitQuestionnaire,
  onClarifyQuestion,
}: MessageItemProps) {
  if (message.role === 'USER') {
    return (
      <div className="message-row user">
        <div className="user-bubble">{message.content}</div>
      </div>
    )
  }

  // A questionnaire card is read-only once it has been answered (a later
  // `questionnaire_complete` exists) or superseded (a later `questionnaire`
  // re-ask exists). Only the latest unanswered card renders the interactive form.
  const completed =
    message.type === 'questionnaire' &&
    messages
      .slice(index + 1)
      .some((m) => m.type === 'questionnaire' || m.type === 'questionnaire_complete')

  return (
    <div className="message-row assistant">
      <div className="assistant-avatar" aria-hidden="true">
        K
      </div>
      <div className="assistant-content">
        <MessageContent
          message={message}
          sessionId={sessionId}
          streaming={streaming}
          completed={completed}
          onSubmitQuestionnaire={onSubmitQuestionnaire}
          onClarifyQuestion={onClarifyQuestion}
        />
      </div>
    </div>
  )
}

export function MessageList({
  messages,
  sessionId,
  streaming,
  onSubmitQuestionnaire,
  onClarifyQuestion,
}: MessageListProps) {
  return (
    <>
      {messages.map((message, index) => (
        <MessageItem
          key={message.id ?? `${message.type}-${index}`}
          message={message}
          index={index}
          messages={messages}
          sessionId={sessionId}
          streaming={streaming}
          onSubmitQuestionnaire={onSubmitQuestionnaire}
          onClarifyQuestion={onClarifyQuestion}
        />
      ))}
    </>
  )
}
