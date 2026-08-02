import { GoogleLogin } from '@react-oauth/google'
import { useState } from 'react'
import { signInWithGoogle, type AuthenticatedUser } from './lib/api'

function App() {
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [error, setError] = useState('')

  async function handleGoogleCredential(credential?: string) {
    if (!credential) return setError('Google did not return a sign-in credential.')
    setError('')
    try {
      const result = await signInWithGoogle(credential)
      sessionStorage.setItem('kapex_token', result.access_token)
      sessionStorage.setItem('kapex_user', JSON.stringify(result.user))
      setUser(result.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in could not be completed.')
    }
  }

  return <main className="page-shell">
    <nav className="nav" aria-label="Main navigation">
      <a className="logo-mark" href="/" aria-label="KapexAI home" />
      <div className="nav-links">
        <a href="#home">Home</a>
        <a href="#menu">Menu</a>
        <a href="#chat">Chat</a>
        <a href="#history">History</a>
        <a href="#graphs">Graphs</a>
      </div>
    </nav>

    <section className="hero" id="home">
      <h1>Where vision meets<br /><em>capital,</em> AI makes it possible</h1>
      <p className="intro">KapexAI is an AI-powered business and trade consulting platform that helps users turn their business ideas into actionable strategies. It generates a visual, step-by-step business plan with cited data, making professional business guidance affordable and accessible.</p>

      {user ? (
        <div className="welcome"><strong>Welcome, {user.name ?? user.email}.</strong><span>You’re signed in and ready to begin.</span></div>
      ) : (
        <div className="auth-block">
          <GoogleLogin onSuccess={({ credential }) => handleGoogleCredential(credential)} onError={() => setError('Google sign-in was cancelled or unavailable.')} theme="outline" shape="rectangular" text="continue_with" width="260" />
          {error && <p className="signin-error" role="alert">{error}</p>}
        </div>
      )}
    </section>
  </main>
}

export default App
