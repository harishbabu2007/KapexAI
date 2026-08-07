/** Animated "thinking" indicator shown while the worker is streaming a reply. */
export function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <div className="assistant-avatar">K</div>
      <div className="typing-indicator" aria-label="Assistant is typing">
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}
