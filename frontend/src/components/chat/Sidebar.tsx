import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { AuthenticatedUser, SessionInfo } from '../../lib/types'

type SidebarProps = {
  sessions: SessionInfo[]
  activeSessionId: string | null
  loading: boolean
  user: AuthenticatedUser | null
  open?: boolean
  onSelect: (id: string) => void
  onRename: (id: string, name: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onNewChat: () => void
  onSignOut: () => void
  onClose?: () => void
}

type MenuState = { id: string; x: number; y: number }

function initials(name?: string | null, email?: string | null): string {
  const source = name || email || 'U'
  return source
    .split(/[\s@]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase())
    .slice(0, 2)
    .join('')
}

export function Sidebar({
  sessions,
  activeSessionId,
  loading,
  user,
  open = false,
  onSelect,
  onRename,
  onDelete,
  onNewChat,
  onSignOut,
  onClose,
}: SidebarProps) {
  const [menu, setMenu] = useState<MenuState | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftName, setDraftName] = useState('')
  const cancelEditRef = useRef(false)
  const navigate = useNavigate()

  const closeMenu = () => {
    setMenu(null)
    setConfirmDeleteId(null)
  }

  function openMenu(event: React.MouseEvent<HTMLButtonElement>, id: string) {
    event.stopPropagation()
    const rect = event.currentTarget.getBoundingClientRect()
    setMenu({ id, x: Math.max(8, rect.right - 176), y: rect.bottom + 4 })
    setConfirmDeleteId(null)
  }

  function startRename(id: string) {
    const session = sessions.find((s) => s.id === id)
    setEditingId(id)
    setDraftName(session?.business_idea || '')
    cancelEditRef.current = false
    closeMenu()
  }

  function commitRename() {
    if (editingId) void onRename(editingId, draftName)
    setEditingId(null)
    setDraftName('')
  }

  function cancelRename() {
    cancelEditRef.current = true
    setEditingId(null)
    setDraftName('')
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (editingId) cancelRename()
        else closeMenu()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [editingId])

  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} />}
      {menu && <div className="session-menu-overlay" onClick={closeMenu} />}
      <aside className={`sidebar${open ? ' open' : ''}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={onNewChat}>
            <span className="new-chat-plus">+</span> New chat
          </button>
        </div>

        <nav className="session-list" aria-label="Chat sessions">
          {loading ? <p className="sidebar-hint">Loading chats…</p> : null}
          {!loading && sessions.length === 0 ? (
            <p className="sidebar-hint">No chats yet. Start one below.</p>
          ) : null}
          {sessions.map((session) =>
            editingId === session.id ? (
              <div key={session.id} className="session-item">
                <input
                  className="session-rename-input"
                  value={draftName}
                  autoFocus
                  onFocus={(e) => e.target.select()}
                  onChange={(e) => setDraftName(e.target.value)}
                  onBlur={() => {
                    if (cancelEditRef.current) {
                      cancelEditRef.current = false
                      return
                    }
                    commitRename()
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitRename()
                    else if (e.key === 'Escape') cancelRename()
                  }}
                />
              </div>
            ) : (
              <div
                key={session.id}
                className={`session-item${session.id === activeSessionId ? ' active' : ''}`}
              >
                <button
                  type="button"
                  className="session-main"
                  onClick={() => {
                    onSelect(session.id)
                    onClose?.()
                  }}
                  title={session.business_idea}
                >
                  <span className="session-icon" aria-hidden="true">
                    ✦
                  </span>
                  <span className="session-title">{session.business_idea || 'Untitled chat'}</span>
                </button>
                <button
                  type="button"
                  className="session-menu-btn"
                  aria-label={`Options for ${session.business_idea || 'Untitled chat'}`}
                  onClick={(e) => openMenu(e, session.id)}
                >
                  <span aria-hidden="true">⋯</span>
                </button>
              </div>
            ),
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="user-chip">
            <span className="user-avatar">{initials(user?.name, user?.email)}</span>
            <span className="user-meta">
              <span className="user-name">{user?.name || 'You'}</span>
              <span className="user-email">{user?.email}</span>
            </span>
          </div>
          <div className="sidebar-footer-actions">
            <button
              type="button"
              className="profile-link-btn"
              onClick={() => {
                onClose?.()
                navigate('/business-profile')
              }}
            >
              Business profile
            </button>
            <button type="button" className="signout-btn" onClick={onSignOut}>
              Log out
            </button>
          </div>
        </div>
      </aside>

      {menu && (
        <div className="session-menu" style={{ left: menu.x, top: menu.y }}>
          {confirmDeleteId ? (
            <div className="session-menu-confirm">
              <p className="confirm-text">
                Delete this chat? All of its messages will be permanently removed.
              </p>
              <div className="confirm-actions">
                <button
                  type="button"
                  className="confirm-cancel"
                  onClick={() => setConfirmDeleteId(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="confirm-danger"
                  onClick={() => {
                    void onDelete(confirmDeleteId)
                    closeMenu()
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                type="button"
                className="session-menu-item"
                onClick={() => startRename(menu.id)}
              >
                Rename
              </button>
              <button
                type="button"
                className="session-menu-item danger"
                onClick={() => setConfirmDeleteId(menu.id)}
              >
                Delete
              </button>
            </>
          )}
        </div>
      )}
    </>
  )
}
