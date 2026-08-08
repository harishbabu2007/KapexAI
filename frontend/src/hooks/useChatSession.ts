import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createSession,
  deleteSession as apiDeleteSession,
  getMessages,
  getSessions,
  pushMessage,
  renameSession as apiRenameSession,
  submitQuestionnaireAnswers as apiSubmitQuestionnaireAnswers,
  submitQuestionnaireClarification as apiSubmitQuestionnaireClarification,
  wsUrl,
} from '../lib/api'
import { useAuth } from '../lib/auth'
import type {
  ChatMessage,
  QuestionnaireAnswer,
  SessionInfo,
  StreamFrame,
  ToolInfo,
} from '../lib/types'

type ChatSessionState = {
  sessions: SessionInfo[]
  activeSessionId: string | null
  messages: ChatMessage[]
  suggestions: ToolInfo[]
  streaming: boolean
  sending: boolean
  questionnairePending: boolean
  loadingSessions: boolean
  loadingMessages: boolean
  error: string | null
  refreshSessions: () => Promise<void>
  selectSession: (id: string) => Promise<void>
  renameSession: (id: string, name: string) => Promise<void>
  deleteSession: (id: string) => Promise<void>
  sendMessage: (text: string) => Promise<void>
  submitQuestionnaireAnswers: (answers: QuestionnaireAnswer[]) => Promise<void>
  clarifyQuestion: (keys: string[], prompt: string) => Promise<void>
  startNewChat: () => void
}

export function useChatSession(): ChatSessionState {
  const { token } = useAuth()

  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [suggestions, setSuggestions] = useState<ToolInfo[]>([])
  const [streaming, setStreaming] = useState(false)
  const [sending, setSending] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const sendingRef = useRef(false)

  // The questionnaire deck is still awaiting answers when the latest
  // questionnaire-related message is a `questionnaire` (asked or re-asked) with
  // no `questionnaire_answer` / `questionnaire_complete` after it.
  const questionnairePending = useMemo(() => {
    let pending = false
    for (const msg of messages) {
      if (msg.type === 'questionnaire') pending = true
      else if (
        msg.type === 'questionnaire_answer' ||
        msg.type === 'questionnaire_complete'
      )
        pending = false
    }
    return pending
  }, [messages])

  useEffect(() => () => wsRef.current?.close(), [])

  const refreshSessions = useCallback(async () => {
    if (!token) return
    setLoadingSessions(true)
    try {
      const { data } = await getSessions(token)
      setSessions([...data].reverse())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load sessions')
    } finally {
      setLoadingSessions(false)
    }
  }, [token])

  useEffect(() => {
    refreshSessions()
  }, [refreshSessions])

  const closeStream = useCallback((ws: WebSocket | null) => {
    if (ws) ws.close()
    if (wsRef.current === ws) wsRef.current = null
  }, [])

  const streamSession = useCallback(
    (sessionId: string) => {
      // Drop any previous socket so overlapping streams can't double-append.
      closeStream(wsRef.current)
      setStreaming(true)
      setSuggestions([])
      setError(null)

      const ws = new WebSocket(wsUrl(sessionId))
      wsRef.current = ws

      ws.onmessage = (event: MessageEvent<string>) => {
        let frame: StreamFrame
        try {
          frame = JSON.parse(event.data) as StreamFrame
        } catch {
          return
        }

        if (frame.event === 'end') {
          closeStream(ws)
          setStreaming(false)
          return
        }
        if (frame.event === 'suggestions') {
          setSuggestions(frame.suggestions || frame.tools || [])
          return
        }
        if (frame.event === 'error') {
          setError(frame.content || frame.message || 'An error occurred')
          closeStream(ws)
          setStreaming(false)
          return
        }

        const newMsg: ChatMessage = {
          id: String(Date.now() + Math.random()),
          session_id: sessionId,
          role: 'assistant',
          type: frame.type || 'chat',
          content: frame.content,
          summary: frame.summary,
          sections: frame.sections,
          questionnaire: frame.questionnaire,
          created_at: new Date().toISOString(),
        }

        setMessages((prev) => [...prev, newMsg])
      }

      ws.onerror = () => {
        setError('Lost connection to the assistant.')
        closeStream(ws)
        setStreaming(false)
      }

      ws.onclose = () => {
        closeStream(ws)
        setStreaming(false)
      }
    },
    [closeStream],
  )

  const loadMessages = useCallback(
    async (sessionId: string) => {
      if (!token) return
      setLoadingMessages(true)
      setSuggestions([])
      setError(null)
      try {
        const { data, pending } = await getMessages(token, sessionId)
        if (pending) {
          // The worker is still replying to this session (e.g. from another
          // tab). Show the in-flight message optimistically and connect to the
          // live stream so the result arrives in real time.
          setMessages([
            ...data,
            {
              role: 'USER',
              type: pending.type ?? 'chat',
              content: pending.content,
              pending: true,
            } as ChatMessage,
          ])
          streamSession(sessionId)
        } else {
          setMessages(data)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not load messages')
        setMessages([])
      } finally {
        setLoadingMessages(false)
      }
    },
    [token, streamSession],
  )

  const selectSession = useCallback(
    async (id: string) => {
      closeStream(wsRef.current)
      setActiveSessionId(id)
      setStreaming(false)
      await loadMessages(id)
    },
    [closeStream, loadMessages],
  )

  const startNewChat = useCallback(() => {
    closeStream(wsRef.current)
    setActiveSessionId(null)
    setMessages([])
    setSuggestions([])
    setStreaming(false)
    setError(null)
  }, [closeStream])

  const renameSession = useCallback(
    async (id: string, name: string) => {
      const trimmed = name.trim()
      if (!token || !trimmed) return
      setError(null)
      try {
        const { business_idea } = await apiRenameSession(token, id, trimmed)
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? { ...s, business_idea } : s)),
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not rename the chat')
      }
    },
    [token],
  )

  const deleteSession = useCallback(
    async (id: string) => {
      if (!token) return
      setError(null)
      try {
        await apiDeleteSession(token, id)
        setSessions((prev) => prev.filter((s) => s.id !== id))
        if (activeSessionId === id) {
          closeStream(wsRef.current)
          setActiveSessionId(null)
          setMessages([])
          setSuggestions([])
          setStreaming(false)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not delete the chat')
      }
    },
    [token, activeSessionId, closeStream],
  )

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !token || streaming || sending) return

      const userMsg: ChatMessage = {
        id: String(Date.now()),
        session_id: activeSessionId || '',
        role: 'user',
        type: 'chat',
        content: trimmed,
        created_at: new Date().toISOString(),
      }

      if (!activeSessionId) {
        setMessages([userMsg])
        setSuggestions([])
        setError(null)
        setSending(true)
        try {
          const { session_id } = await createSession(token, trimmed)
          setActiveSessionId(session_id)
          refreshSessions()
          streamSession(session_id)
        } catch (err) {
          setMessages([])
          setError(err instanceof Error ? err.message : 'Could not start a chat')
        } finally {
          setSending(false)
        }
        return
      }

      setMessages((prev) => [...prev, userMsg])
      setSuggestions([])
      setError(null)
      setSending(true)
      try {
        await pushMessage(token, activeSessionId, trimmed)
        streamSession(activeSessionId)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not send the message')
      } finally {
        setSending(false)
      }
    },
    [activeSessionId, token, streaming, sending, refreshSessions, streamSession],
  )

  const submitQuestionnaireAnswers = useCallback(
    async (answers: QuestionnaireAnswer[]) => {
      if (!token || !activeSessionId || streaming || sending) return
      if (sendingRef.current) return
      sendingRef.current = true
      setSending(true)
      setError(null)
      // Optimistically echo the answers (mirrors the worker's `_format_answers`).
      const content = answers
        .map((a, i) => `${i + 1}) ${a.answer || 'Skipped'}`)
        .join('\n')
      setMessages((prev) => [
        ...prev,
        { role: 'USER', type: 'questionnaire_answer', content },
      ])
      try {
        await apiSubmitQuestionnaireAnswers(token, activeSessionId, answers)
        streamSession(activeSessionId)
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Could not submit the questionnaire',
        )
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [activeSessionId, token, streaming, sending, streamSession],
  )

  const clarifyQuestion = useCallback(
    async (keys: string[], prompt: string) => {
      if (!token || !activeSessionId || streaming || sending) return
      if (sendingRef.current) return
      sendingRef.current = true
      setSending(true)
      setError(null)
      setMessages((prev) => [
        ...prev,
        { role: 'USER', type: 'chat', content: prompt },
      ])
      try {
        await apiSubmitQuestionnaireClarification(token, activeSessionId, keys)
        streamSession(activeSessionId)
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : 'Could not ask for a simpler explanation',
        )
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [activeSessionId, token, streaming, sending, streamSession],
  )

  return {
    sessions,
    activeSessionId,
    messages,
    suggestions,
    streaming,
    sending,
    questionnairePending,
    loadingSessions,
    loadingMessages,
    error,
    refreshSessions,
    selectSession,
    renameSession,
    deleteSession,
    sendMessage,
    submitQuestionnaireAnswers,
    clarifyQuestion,
    startNewChat,
  }
}
