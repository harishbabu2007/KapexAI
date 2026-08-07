import { GoogleLogin } from '@react-oauth/google'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

/**
 * "Sign in with Google" popup button. On success the Google ID token is
 * exchanged for a KapexAI JWT via `POST /auth/google` and stored by the
 * AuthProvider.
 */
export function GoogleSignInButton({ width = 260 }: { width?: number }) {
  const { signInWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  function handleCredential(credential?: string) {
    if (!credential) {
      setError('Google did not return a sign-in credential.')
      return
    }
    setError('')
    signInWithGoogle(credential)
      .then(() => navigate('/chat'))
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Google sign-in could not be completed.'),
      )
  }

  return (
    <div className="google-signin">
      <GoogleLogin
        onSuccess={({ credential }) => handleCredential(credential)}
        onError={() => setError('Google sign-in was cancelled or unavailable.')}
        theme="outline"
        shape="rectangular"
        text="continue_with"
        width={width}
      />
      {error && (
        <p className="signin-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
