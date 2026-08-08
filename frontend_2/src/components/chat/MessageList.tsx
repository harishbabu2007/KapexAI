import type { ChatMessage } from '../../lib/types'
import { renderMessageCard } from '../messages'

interface MessageListProps {
  messages: ChatMessage[]
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((msg) => (
        <div key={msg.id} className={`message-row ${msg.role}`}>
          <div className="message-bubble">
            {msg.role === 'user' ? (
              <div className="user-text">{msg.content}</div>
            ) : (
              renderMessageCard(msg)
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
