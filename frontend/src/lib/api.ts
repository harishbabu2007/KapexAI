const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type AuthenticatedUser = { id: string; email: string; name: string | null }

export async function signInWithGoogle(credential: string) {
  const response = await fetch(`${API_BASE_URL}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  })

  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail ?? 'Google sign-in could not be completed.')
  return body as { access_token: string; user: AuthenticatedUser }
}
