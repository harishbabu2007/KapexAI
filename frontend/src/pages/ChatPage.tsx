import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatHeader } from '../components/chat/ChatHeader'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { NewChatHero } from '../components/chat/NewChatHero'
import { Sidebar } from '../components/chat/Sidebar'
import { Suggestions } from '../components/chat/Suggestions'
import { TabBlockedOverlay } from '../components/chat/TabBlockedOverlay'
import { TypingIndicator } from '../components/chat/TypingIndicator'
import {
  EMPTY_DRAFT,
  FeedbackDialog,
} from '../components/feedback/FeedbackDialog'
import type { FeedbackDraft } from '../components/feedback/FeedbackDialog'
import { describeFeedbackError, submitFeedback } from '../lib/api'
import { createFeedbackLifecycle } from '../lib/feedbackLifecycle'
import type { FeedbackResult } from '../lib/feedbackLifecycle'
import { useAuth } from '../lib/auth'
import type { ToolInfo } from '../lib/types'
import { useChatSession } from '../hooks/useChatSession'
import { useSingleTab } from '../hooks/useSingleTab'

export function ChatPage() {
  const { user, signOut, token, feedbackEnabled } = useAuth()
  const chat = useChatSession()
  const { blocked, claimTab } = useSingleTab()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  // Whichever control opened the dialog, so focus can be handed back to it.
  const feedbackTriggerRef = useRef<HTMLElement | null>(null)

  // ── Feedback submission ownership ────────────────────────────
  // The dialog unmounts when it closes, so the draft and the whole request
  // lifecycle live here. Closing the dialog therefore only hides it: it neither
  // cancels the request (cancelling a fetch does not prove no row was written)
  // nor clears `feedbackResult` (which would discard the outcome).
  const [feedbackDraft, setFeedbackDraft] = useState<FeedbackDraft>(EMPTY_DRAFT)
  const [feedbackResult, setFeedbackResult] = useState<FeedbackResult | null>(null)
  // The lifecycle holds the pending flag, the sequence guard and the abort
  // controller. It exposes no way to cancel a submission, so "hide the dialog"
  // cannot accidentally clear a pending request. Created once; `send` receives
  // the payload per call, so no render-scoped value is captured.
  const lifecycleRef = useRef<ReturnType<typeof createFeedbackLifecycle<FeedbackDraft>> | null>(null)
  if (lifecycleRef.current === null) {
    lifecycleRef.current = createFeedbackLifecycle<FeedbackDraft>({
      send: (payload, signal) => {
        if (!token) return Promise.reject(new Error('not signed in'))
        return submitFeedback(
          token,
          {
            category: payload.category,
            message: payload.message.trim(),
            contact_allowed: payload.contactAllowed,
            session_id: chat.activeSessionId,
            page_path: typeof window === 'undefined' ? null : window.location.pathname,
          },
          signal,
        )
      },
      describeError: describeFeedbackError,
      onChange: setFeedbackResult,
    })
  }

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

  // Opening never touches the request or its result, so reopening mid-flight
  // shows the pending state (and the eventual outcome) instead of a fresh form.
  const openFeedback = useCallback((trigger: HTMLElement | null) => {
    feedbackTriggerRef.current = trigger
    setFeedbackOpen(true)
  }, [])

  const closeFeedback = useCallback(() => setFeedbackOpen(false), [])

  const resetFeedback = useCallback(() => {
    // Only reachable once a request has settled, so no outcome is discarded.
    setFeedbackDraft(EMPTY_DRAFT)
    setFeedbackResult(null)
  }, [])

  // Delegates to the lifecycle, which ignores the call while a request is on the
  // wire. `onClose` above deliberately does not touch any of this.
  const submitFeedbackDraft = useCallback((draft: FeedbackDraft) => {
    void lifecycleRef.current?.submit(draft)
  }, [])

  // Cleanup only. This stops the socket being held open by an unmounted page;
  // it does NOT establish that the backend skipped the write, which is why an
  // abort surfaces as `delivery: "uncertain"` in the lifecycle.
  useEffect(() => () => lifecycleRef.current?.abort(), [])

  if (blocked) {
    return <TabBlockedOverlay onClaim={handleClaim} />
  }

  const feedbackAvailable = Boolean(token && feedbackEnabled)

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
        feedbackEnabled={feedbackAvailable}
        onOpenFeedback={openFeedback}
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
              title={activeSession?.business_idea}
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
          <>
            {/*
              The empty-chat state has no header of its own, so on mobile there
              would be no way to reach the sidebar (and with it Feedback). This
              reuses ChatHeader purely for its menu toggle and is hidden on
              desktop, where the sidebar is always visible.
            */}
            <div className="chat-empty-header">
              <ChatHeader onMenu={() => setSidebarOpen(true)} />
            </div>
            <div className="message-scroll new-chat-scroll">
              <NewChatHero
                onSend={chat.sendMessage}
                streaming={chat.streaming || chat.sending}
              />
            </div>
          </>
        )}
      </main>

      {feedbackOpen && feedbackAvailable && (
        <FeedbackDialog
          triggerRef={feedbackTriggerRef}
          draft={feedbackDraft}
          onDraftChange={setFeedbackDraft}
          result={feedbackResult}
          onSubmit={submitFeedbackDraft}
          onReset={resetFeedback}
          onClose={closeFeedback}
        />
      )}
    </div>
  )
}
