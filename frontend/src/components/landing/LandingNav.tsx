import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

export function LandingNav() {
  const { user } = useAuth()
  const navigate = useNavigate()

  return (
    <nav className="nav" aria-label="Main navigation">
      <a className="logo-mark" href="#home" aria-label="KapexAI home" />
      <div className="nav-links">
        <a href="#home">Home</a>
        <a href="#features">Features</a>
      </div>
      <div className="nav-auth">
        {user ? (
          <button type="button" className="nav-open-chat" onClick={() => navigate('/chat')}>
            Open chat
          </button>
        ) : (
          <a className="nav-signin" href="#home">
            Sign in
          </a>
        )}
      </div>
    </nav>
  )
}
