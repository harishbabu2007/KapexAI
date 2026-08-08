import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createSession,
  deleteSession as apiDeleteSession,
  getMessages,
  getSessions,
  pushMessage,
  renameSession as apiRenameSession,
  wsUrl,
} from '../lib/api'
import { useAuth } from '../lib/auth'
import type { ChatMessage, SessionInfo, StreamFrame, ToolInfo } from '../lib/types'

type ChatSessionState = {
  sessions: SessionInfo[]
  activeSessionId: string | null
  messages: ChatMessage[]
  suggestions: ToolInfo[]
  streaming: boolean
  sending: boolean
  loadingSessions: boolean
  loadingMessages: boolean
  error: string | null
  refreshSessions: () => Promise<void>
  selectSession: (id: string) => Promise<void>
  renameSession: (id: string, name: string) => Promise<void>
  deleteSession: (id: string) => Promise<void>
  sendMessage: (text: string) => Promise<void>
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
        const { data } = await getMessages(token, sessionId)
        setMessages(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not load messages')
        setMessages([])
      } finally {
        setLoadingMessages(false)
      }
    },
    [token],
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

  return {
    sessions,
    activeSessionId,
    messages,
    suggestions,
    streaming,
    sending,
    loadingSessions,
    loadingMessages,
    error,
    refreshSessions,
    selectSession,
    renameSession,
    deleteSession,
    sendMessage,
    startNewChat,
  }
}
