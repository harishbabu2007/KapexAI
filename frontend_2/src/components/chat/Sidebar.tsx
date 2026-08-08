import { useState } from 'react'
import type { SessionInfo } from '../../lib/types'
import type { UserInfo } from '../../lib/auth'

interface SidebarProps {
  sessions: SessionInfo[]
  activeSessionId: string | null
  loading: boolean
  user: UserInfo | null
  open: boolean
  onSelect: (id: string) => void
  onRename: (id: string, newIdea: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onNewChat: () => void
  onSignOut: () => void
  onClose: () => void
}

export function Sidebar({
  sessions,
  activeSessionId,
  loading,
  user,
  open,
  onSelect,
  onRename,
  onDelete,
  onNewChat,
  onSignOut,
  onClose,
}: SidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [menuId, setMenuId] = useState<string | null>(null)

  function startEditing(session: SessionInfo) {
    setEditingId(session.id)
    setEditValue(session.business_idea ?? '')
    setMenuId(null)
  }

  async function saveRename(id: string) {
    if (!editValue.trim()) return
    await onRename(id, editValue.trim())
    setEditingId(null)
  }

  return (
    <>
      <div className={`sidebar-backdrop ${open ? 'open' : ''}`} onClick={onClose} />
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-header">
          <button type="button" className="new-chat-btn" onClick={onNewChat}>
            + New Consulting Session
          </button>
        </div>

        <div className="sidebar-sessions">
          {loading ? (
            <div className="sidebar-loading">Loading sessions…</div>
          ) : sessions.length === 0 ? (
            <div className="sidebar-empty">No sessions yet. Start one above!</div>
          ) : (
            sessions.map((s) => {
              const isActive = s.id === activeSessionId
              const isEditing = s.id === editingId
              return (
                <div key={s.id} className={`session-item ${isActive ? 'active' : ''}`}>
                  {isEditing ? (
                    <div className="session-edit-box">
                      <input
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveRename(s.id)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                      />
                      <button type="button" onClick={() => saveRename(s.id)}>
                        ✓
                      </button>
                    </div>
                  ) : (
                    <div className="session-row" onClick={() => onSelect(s.id)}>
                      <span className="session-title">
                        {s.business_idea || 'Untitled Consulting Session'}
                      </span>
                      <div className="session-actions">
                        <button
                          type="button"
                          className="menu-toggle"
                          onClick={(e) => {
                            e.stopPropagation()
                            setMenuId(menuId === s.id ? null : s.id)
                          }}
                          aria-label="Session options"
                        >
                          ⋯
                        </button>
                        {menuId === s.id && (
                          <div className="session-dropdown" onClick={(e) => e.stopPropagation()}>
                            <button type="button" onClick={() => startEditing(s)}>
                              Rename
                            </button>
                            <button
                              type="button"
                              className="delete-btn"
                              onClick={() => {
                                onDelete(s.id)
                                setMenuId(null)
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        <div className="sidebar-footer">
          {user && (
            <div className="user-profile">
              <div className="user-info">
                <span className="user-name">{user.name ?? user.email}</span>
                <span className="user-email">{user.email}</span>
              </div>
              <button type="button" className="signout-btn" onClick={onSignOut} title="Sign out">
                ⎋
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
