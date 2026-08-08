import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getBusinessProfile, updateBusinessProfile } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { BusinessProfile } from '../lib/types'

const EMPTY: BusinessProfile = {
  your_name: '',
  industry: '',
  about_you: '',
  business_history: '',
  location: '',
  monthly_income: '',
  monthly_expenditure: '',
}

type FieldDef = {
  key: keyof BusinessProfile
  label: string
  hint?: string
  textarea?: boolean
}

const BUSINESS_FIELDS: FieldDef[] = [
  { key: 'your_name', label: 'Your name' },
  { key: 'industry', label: 'Industry' },
  {
    key: 'about_you',
    label: 'About you',
    hint: 'Your background, skills, or what you bring to the table.',
    textarea: true,
  },
  {
    key: 'business_history',
    label: 'Businesses you own or have run',
    hint: 'Past or currently running businesses — anything relevant.',
    textarea: true,
  },
  { key: 'location', label: 'Location' },
]

const FINANCIAL_FIELDS: FieldDef[] = [
  {
    key: 'monthly_income',
    label: 'Monthly income',
    hint: 'A rough estimate is fine.',
  },
  {
    key: 'monthly_expenditure',
    label: 'Monthly expenditure',
    hint: 'Roughly what the business spends per month.',
  },
]

export function BusinessProfilePage() {
  const { token, signOut, markProfileFilled, user } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState<BusinessProfile>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!token) {
      setLoading(false)
      return
    }
    getBusinessProfile(token)
      .then(({ data }) => {
        if (cancelled) return
        setForm({ ...EMPTY, ...data })
      })
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : 'Could not load your profile.',
        ),
      )
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  function setField(key: keyof BusinessProfile, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setError('')
  }

  async function handleSave() {
    if (!token || saving) return
    setSaving(true)
    setError('')
    try {
      await updateBusinessProfile(token, form)
      markProfileFilled()
      navigate('/chat')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not save your profile.',
      )
      setSaving(false)
    }
  }

  function renderFields(fields: FieldDef[]) {
    return fields.map((field) => (
      <label className="profile-field" key={field.key}>
        <span className="profile-field-label">
          {field.label}
          {field.hint ? <span className="profile-field-hint">{field.hint}</span> : null}
        </span>
        {field.textarea ? (
          <textarea
            className="profile-input profile-input-textarea"
            value={form[field.key] ?? ''}
            onChange={(e) => setField(field.key, e.target.value)}
            rows={3}
          />
        ) : (
          <input
            className="profile-input"
            type="text"
            value={form[field.key] ?? ''}
            onChange={(e) => setField(field.key, e.target.value)}
          />
        )}
      </label>
    ))
  }

  return (
    <div className="profile-layout">
      <header className="profile-header">
        <div className="profile-header-title">
          <span className="profile-logo" aria-hidden="true">
            K
          </span>
          <div>
            <h1>Business profile</h1>
            <p className="profile-subtitle">
              A little about you so KapexAI doesn&apos;t have to ask every time.
            </p>
          </div>
        </div>
        <div className="profile-header-actions">
          <button
            type="button"
            className="profile-back-btn"
            onClick={() => navigate('/chat')}
          >
            ← Back to chat
          </button>
          <button type="button" className="signout-btn" onClick={signOut}>
            Log out
          </button>
        </div>
      </header>

      <main className="profile-main">
        {loading ? (
          <div className="message-loading">Loading your profile…</div>
        ) : (
          <>
            {error && (
              <div className="chat-error-banner" role="alert">
                {error}
              </div>
            )}

            <section className="profile-section">
              <h2>Business profile</h2>
              <div className="profile-grid">{renderFields(BUSINESS_FIELDS)}</div>
            </section>

            <section className="profile-section">
              <h2>Financial info</h2>
              <div className="profile-grid">{renderFields(FINANCIAL_FIELDS)}</div>
            </section>

            <div className="profile-actions">
              <button
                type="button"
                className="send-btn"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save profile'}
              </button>
              <button
                type="button"
                className="profile-skip-btn"
                onClick={() => navigate('/chat')}
              >
                Skip for now
              </button>
            </div>
          </>
        )}
      </main>

      <footer className="profile-footer">
        <span>Signed in as {user?.email}</span>
      </footer>
    </div>
  )
}