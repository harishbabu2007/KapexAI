type ChatHeaderProps = {
  title?: string
  onMenu?: () => void
}

/** Sticky bar at the top of the conversation. */
export function ChatHeader({ title, onMenu }: ChatHeaderProps) {
  return (
    <header className="chat-header">
      {onMenu && (
        <button type="button" className="menu-toggle" onClick={onMenu} aria-label="Open sidebar">
          <span />
          <span />
          <span />
        </button>
      )}
      <h1 className="chat-header-title">{title || 'New chat'}</h1>
    </header>
  )
}
