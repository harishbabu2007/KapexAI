import { useState } from 'react'

type ComposerProps = {
  onSend: (text: string) => void
  disabled: boolean
  placeholder?: string
}

/** Chat input with send button. Enter submits, Shift+Enter adds a newline. */
export function Composer({ onSend, disabled, placeholder = 'Message KapexAI…' }: ComposerProps) {
  const [text, setText] = useState('')

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  return (
    <div className="composer-wrap">
      <textarea
        className="composer-input"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
        placeholder={placeholder}
        rows={1}
        disabled={disabled}
        aria-label="Message"
      />
      <button
        type="button"
        className="send-btn"
        onClick={submit}
        disabled={disabled || !text.trim()}
        aria-label="Send message"
      >
        Send
      </button>
    </div>
  )
}
