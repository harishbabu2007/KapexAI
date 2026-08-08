import { useEffect, useRef, useState } from 'react'
import { ChatHeader } from '../components/chat/ChatHeader'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { NewChatHero } from '../components/chat/NewChatHero'
import { Sidebar } from '../components/chat/Sidebar'
import { Suggestions } from '../components/chat/Suggestions'
import { TypingIndicator } from '../components/chat/TypingIndicator'
import { useAuth } from '../lib/auth'
import type { ToolInfo } from '../lib/types'
import { useChatSession } from '../hooks/useChatSession'

export function ChatPage() {
  const { user, signOut } = useAuth()
  const chat = useChatSession()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const activeSession = chat.sessions.find((s) => s.id === chat.activeSessionId)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages, chat.streaming, chat.suggestions])

  function handleSuggestion(tool: ToolInfo) {
    chat.sendMessage(tool.example)
  }

  return (
    <div className="chat-layout">
      <Sidebar
        sessions={chat.sessions}
        activeSessionId={chat.activeSessionId}
        loading={chat.loadingSessions}
        user={user}
        open={sidebarOpen}
        onSelect={chat.selectSession}
        onRename={chat.renameSession}
        onDelete={chat.deleteSession}
        onNewChat={chat.startNewChat}
        onSignOut={signOut}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="chat-main">
        {chat.error && (
          <div className="chat-error-banner" role="alert">
            {chat.error}
          </div>
        )}

        {chat.activeSessionId ? (
          <>
            <ChatHeader
              title={activeSession?.business_idea ?? undefined}
              onMenu={() => setSidebarOpen(true)}
            />
            <div className="message-scroll">
              {chat.loadingMessages ? (
                <div className="message-loading">Loading conversation…</div>
              ) : (
                <MessageList messages={chat.messages} />
              )}
              {chat.streaming && <TypingIndicator />}
              {chat.suggestions.length > 0 && (
                <Suggestions suggestions={chat.suggestions} onPick={handleSuggestion} />
              )}
              <div ref={bottomRef} />
            </div>
            <Composer
              key={chat.activeSessionId}
              onSend={chat.sendMessage}
              disabled={chat.streaming || chat.sending}
            />
          </>
        ) : (
          <div className="message-scroll new-chat-scroll">
            <NewChatHero
              onSend={chat.sendMessage}
              streaming={chat.streaming || chat.sending}
            />
          </div>
        )}
      </main>
    </div>
  )
}
