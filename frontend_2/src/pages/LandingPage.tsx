import { useNavigate } from 'react-router-dom'
import { GoogleSignInButton } from '../components/auth/GoogleSignInButton'
import { Features } from '../components/landing/Features'
import { LandingNav } from '../components/landing/LandingNav'
import { useAuth } from '../lib/auth'

export function LandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()

  return (
    <main className="page-shell">
      <LandingNav />

      <section className="hero" id="home">
        <h1>
          Where vision meets <em>capital,</em> AI makes it possible
        </h1>
        <p className="intro">
          KapexAI is an AI-powered business and trade consulting platform that helps users turn
          their business ideas into actionable strategies. It generates a visual, step-by-step
          business plan with cited data, making professional business guidance affordable and
          accessible.
        </p>

        {loading ? (
          <div className="auth-block">
            <div className="spinner" aria-label="Checking session" />
          </div>
        ) : user ? (
          <div className="welcome">
            <strong>Welcome, {user.name ?? user.email}.</strong>
            <span>You&apos;re signed in and ready to begin.</span>
            <button type="button" className="cta-button" onClick={() => navigate('/chat')}>
              Open your chat workspace
            </button>
          </div>
        ) : (
          <div className="auth-block">
            <GoogleSignInButton width={280} />
            <p className="hero-hint">Free while in beta.</p>
          </div>
        )}
      </section>

      <Features />

      <footer className="footer">
        <span className="footer-mark" aria-hidden="true" />
        <span>© {new Date().getFullYear()} KapexAI</span>
        <a href="#home">Back to top</a>
      </footer>
    </main>
  )
}
