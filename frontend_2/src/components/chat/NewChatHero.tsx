import { useState } from 'react'

type NewChatHeroProps = {
  onSend: (text: string) => void
  streaming: boolean
}

/**
 * Landing screen shown when no conversation is selected. The user describes
 * their business idea here to create the first session.
 */
export function NewChatHero({ onSend, streaming }: NewChatHeroProps) {
  const [text, setText] = useState('')

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || streaming) return
    onSend(trimmed)
  }

  return (
    <div className="new-chat-hero">
      <h2 className="new-chat-title">
        Where vision meets <em>capital</em>
      </h2>
      <p className="new-chat-subtitle">
        Describe your business idea and KapexAI will help you shape it — with
        research, SWOT analysis and a step-by-step plan.
      </p>
      <div className="new-chat-box">
        <textarea
          className="new-chat-input"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder="e.g. An AI-powered market research tool for small retailers in Pune…"
          rows={3}
          disabled={streaming}
          autoFocus
          aria-label="Business idea"
        />
        <div className="new-chat-actions">
          <button
            type="button"
            className="send-btn send-btn-lg"
            onClick={submit}
            disabled={streaming || !text.trim()}
          >
            {streaming ? 'Working…' : 'Get started'}
          </button>
        </div>
      </div>
    </div>
  )
}
