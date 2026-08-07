import type { ChatMessage } from '../../lib/types'
import { MessageContent } from '../messages'

function MessageItem({ message }: { message: ChatMessage }) {
  if (message.role === 'USER') {
    return (
      <div className="message-row user">
        <div className="user-bubble">{message.content}</div>
      </div>
    )
  }

  return (
    <div className="message-row assistant">
      <div className="assistant-avatar" aria-hidden="true">
        K
      </div>
      <div className="assistant-content">
        <MessageContent message={message} />
      </div>
    </div>
  )
}

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <>
      {messages.map((message, index) => (
        <MessageItem
          key={message.id ?? `${message.type}-${index}`}
          message={message}
        />
      ))}
    </>
  )
}
