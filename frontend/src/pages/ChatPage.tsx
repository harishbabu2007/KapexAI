import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatHeader } from '../components/chat/ChatHeader'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { NewChatHero } from '../components/chat/NewChatHero'
import { Sidebar } from '../components/chat/Sidebar'
import { Suggestions } from '../components/chat/Suggestions'
import { TabBlockedOverlay } from '../components/chat/TabBlockedOverlay'
import { TypingIndicator } from '../components/chat/TypingIndicator'
import { useAuth } from '../lib/auth'
import type { ToolInfo } from '../lib/types'
import { useChatSession } from '../hooks/useChatSession'
import { useSingleTab } from '../hooks/useSingleTab'

export function ChatPage() {
  const { user, signOut } = useAuth()
  const chat = useChatSession()
  const { blocked, claimTab } = useSingleTab()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const activeSession = chat.sessions.find((s) => s.id === chat.activeSessionId)

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  // Anchor to the bottom when the user sends a message (streaming starts) so
  // their bubble and the typing indicator are visible.
  useEffect(() => {
    if (chat.streaming) scrollToBottom()
  }, [chat.streaming, scrollToBottom])

  // When switching sessions, land at the bottom once the history is loaded.
  // Incoming messages never auto-scroll — the user stays where they are.
  useEffect(() => {
    if (!chat.loadingMessages && chat.activeSessionId) scrollToBottom()
  }, [chat.loadingMessages, chat.activeSessionId, scrollToBottom])

  function handleSuggestion(tool: ToolInfo) {
    chat.sendMessage(tool.example)
  }

  function handleClaim() {
    // Take over the session here and resync this tab with the latest state.
    claimTab()
    chat.refreshSessions()
    if (chat.activeSessionId) chat.selectSession(chat.activeSessionId)
  }

  if (blocked) {
    return <TabBlockedOverlay onClaim={handleClaim} />
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
            <div className="message-scroll" ref={scrollRef}>
              {chat.loadingMessages ? (
                <div className="message-loading">Loading conversation…</div>
              ) : (
                <MessageList
                  messages={chat.messages}
                  sessionId={chat.activeSessionId ?? undefined}
                  streaming={chat.streaming}
                  onSubmitQuestionnaire={chat.submitQuestionnaireAnswers}
                  onClarifyQuestion={chat.clarifyQuestion}
                />
              )}
              {chat.streaming && <TypingIndicator />}
              {chat.suggestions.length > 0 && (
                <Suggestions suggestions={chat.suggestions} onPick={handleSuggestion} />
              )}
            </div>
            <Composer
              key={chat.activeSessionId}
              onSend={chat.sendMessage}
              disabled={
                chat.streaming || chat.sending || chat.questionnairePending
              }
              placeholder={
                chat.questionnairePending
                  ? 'Answer the questions above to continue…'
                  : undefined
              }
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
