import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getMe, signInWithGoogle, ApiError } from './api'
import type { AuthenticatedUser } from './types'

const TOKEN_KEY = 'kapex_token'
const USER_KEY = 'kapex_user'

type AuthContextValue = {
  user: AuthenticatedUser | null
  token: string | null
  /** True while the session is being restored from storage / validated. */
  loading: boolean
  signInWithGoogle: (credential: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredSession(): { token: string; user: AuthenticatedUser } | null {
  const token = localStorage.getItem(TOKEN_KEY)
  const rawUser = localStorage.getItem(USER_KEY)
  if (!token) return null
  try {
    return { token, user: JSON.parse(rawUser ?? 'null') as AuthenticatedUser }
  } catch {
    return { token, user: { id: '', email: '', name: null } }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function restore() {
      const stored = readStoredSession()
      if (!stored) {
        setLoading(false)
        return
      }

      try {
        // Validate the stored token against the backend so stale/expired
        // sessions are dropped instead of being trusted blindly.
        const fresh = await getMe(stored.token)
        if (cancelled) return
        localStorage.setItem(USER_KEY, JSON.stringify(fresh))
        setToken(stored.token)
        setUser(fresh)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          // Token was rejected — drop the stored session.
          localStorage.removeItem(TOKEN_KEY)
          localStorage.removeItem(USER_KEY)
          setToken(null)
          setUser(null)
        } else {
          // Transient failure (network, backend down) — keep the stored
          // session so a hiccup doesn't log the user out.
          setToken(stored.token)
          setUser(stored.user)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    restore()
    return () => {
      cancelled = true
    }
  }, [])

  const signInWithGoogleCallback = useCallback(async (credential: string) => {
    const result = await signInWithGoogle(credential)
    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(result.user))
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, token, loading, signInWithGoogle: signInWithGoogleCallback, signOut }),
    [user, token, loading, signInWithGoogleCallback, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
