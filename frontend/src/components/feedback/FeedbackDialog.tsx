import { useCallback, useEffect, useRef } from 'react'
import type { FeedbackFailure } from '../../lib/api'
import type { FeedbackResult } from '../../lib/feedbackLifecycle'
import type { FeedbackCategory } from '../../lib/types'

const MAX_MESSAGE_CHARS = 2000

const CATEGORIES: { value: FeedbackCategory; label: string; hint: string }[] = [
  { value: 'bug', label: 'Bug', hint: 'Something is broken or behaves unexpectedly' },
  { value: 'feature_request', label: 'Feature request', hint: 'An idea for something new' },
  { value: 'general', label: 'General', hint: 'Anything else' },
]

/** The form contents. Owned by the parent so they survive closing the dialog. */
export type FeedbackDraft = {
  category: FeedbackCategory
  message: string
  contactAllowed: boolean
}

export const EMPTY_DRAFT: FeedbackDraft = {
  category: 'bug',
  message: '',
  contactAllowed: false,
}

type FeedbackDialogProps = {
  /** The control that opened the dialog; focus returns here on close. */
  triggerRef: React.RefObject<HTMLElement | null>
  draft: FeedbackDraft
  onDraftChange: (draft: FeedbackDraft) => void
  result: FeedbackResult | null
  /**
   * Asks the parent to submit. The parent's lifecycle ignores this while a
   * request is already on the wire.
   */
  onSubmit: (draft: FeedbackDraft) => void
  /** Clears the draft and the result so a new submission can be composed. */
  onReset: () => void
  /** Hides the dialog. Deliberately does not touch the request or its result. */
  onClose: () => void
}

/**
 * Accessible feedback form.
 *
 * This component owns no request state at all: the draft, the pending flag and
 * the outcome all live in the parent, because this component unmounts when the
 * dialog closes. Anything kept locally would be lost at exactly the moment it
 * matters most — while a submission is in flight and its result has not
 * arrived. That is why `onClose` only hides the dialog. It does not cancel the
 * request (cancelling a fetch does not establish that no row was written, so it
 * would destroy the only chance of learning the outcome) and it does not clear
 * the pending state (which would invite a second row).
 */
export function FeedbackDialog({
  triggerRef,
  draft,
  onDraftChange,
  result,
  onSubmit,
  onReset,
  onClose,
}: FeedbackDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const messageRef = useRef<HTMLTextAreaElement>(null)

  const pending = result?.phase === 'pending'
  const delivered = result?.phase === 'delivered' ? result : null
  const failed = result?.phase === 'failed' ? result.failure : null

  const trimmed = draft.message.trim()
  const canSubmit = trimmed.length > 0 && !pending

  useEffect(() => {
    messageRef.current?.focus()
  }, [])

  const handleClose = useCallback(() => {
    // Hide only. The in-flight request and its eventual result are the parent's
    // to keep, and focus goes back to whatever opened the dialog.
    onClose()
    // The trigger may re-render/unmount first, so defer the focus call.
    requestAnimationFrame(() => triggerRef.current?.focus())
  }, [onClose, triggerRef])

  // Escape closes even mid-request; the request is untouched.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        handleClose()
        return
      }
      if (event.key !== 'Tab') return
      // `aria-modal` promises the rest of the page is inert to assistive tech,
      // which is only true if focus cannot leave the dialog. Wrap Tab around the
      // focusable elements instead of letting it escape to the sidebar.
      const root = dialogRef.current
      if (!root) return
      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (event.shiftKey && (active === first || !root.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [handleClose])

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    onSubmit(draft)
  }

  return (
    <div
      className="feedback-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) handleClose()
      }}
    >
      <div
        className="feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-dialog-title"
        ref={dialogRef}
      >
        <div className="feedback-dialog-head">
          <h2 className="feedback-dialog-title" id="feedback-dialog-title">
            Send feedback
          </h2>
          <button
            type="button"
            className="feedback-dialog-close"
            onClick={handleClose}
            aria-label="Close feedback dialog"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        {delivered ? (
          <div className="feedback-success" role="status">
            <p className="feedback-success-line">
              Thanks — your feedback was recorded.
            </p>
            <p className="feedback-success-ref">
              Reference: <code>{delivered.feedbackId}</code>
            </p>
            <p className="feedback-success-hint">
              {draft.contactAllowed
                ? 'We may email you about this.'
                : 'We did not save your email address with this feedback.'}
            </p>
            <div className="feedback-actions">
              <button type="button" className="feedback-btn feedback-btn-ghost" onClick={handleClose}>
                Close
              </button>
              <button
                type="button"
                className="feedback-btn feedback-btn-primary"
                onClick={() => {
                  onReset()
                  messageRef.current?.focus()
                }}
              >
                Send more
              </button>
            </div>
          </div>
        ) : (
          <form className="feedback-form" onSubmit={handleSubmit} noValidate>
            {pending && (
              <div className="feedback-pending" role="status">
                <p className="feedback-pending-line">
                  Sending your feedback…
                </p>
                <p className="feedback-pending-note">
                  You can close this dialog — it will keep sending, and reopening
                  it will show you the result. Please don’t send a second one
                  until it finishes.
                </p>
              </div>
            )}

            {!pending && failed?.delivery === 'uncertain' && (
              <div className="feedback-error warning" role="alert">
                <p className="feedback-error-line">{failed.message}</p>
                <p className="feedback-error-note">
                  We could not confirm this was saved, so it may already be in our
                  sheet. Sending it again may create a duplicate.
                </p>
                {failed.feedbackId && (
                  <p className="feedback-error-ref">
                    Reference: <code>{failed.feedbackId}</code>
                  </p>
                )}
                {failed.retryAfterSeconds && (
                  <p className="feedback-error-note">
                    You can send another in about {failed.retryAfterSeconds} seconds.
                  </p>
                )}
                {failed.code && (
                  <p className="feedback-error-code">
                    Code: <code>{failed.code}</code>
                  </p>
                )}
              </div>
            )}

            {!pending && failed && failed.delivery !== 'uncertain' && (
              <div className="feedback-error" role="alert">
                <p className="feedback-error-line">{failed.message}</p>
                {failed.feedbackId && (
                  <p className="feedback-error-ref">
                    Reference: <code>{failed.feedbackId}</code>
                  </p>
                )}
                {failed.retryAfterSeconds && (
                  <p className="feedback-error-note">
                    You can send another in about {failed.retryAfterSeconds} seconds.
                  </p>
                )}
                {failed.code && (
                  <p className="feedback-error-code">
                    Code: <code>{failed.code}</code>
                  </p>
                )}
              </div>
            )}

            <fieldset className="feedback-fieldset" disabled={pending}>
              <legend className="feedback-label">What is this about?</legend>
              <div className="feedback-categories" role="radiogroup" aria-label="Feedback category">
                {CATEGORIES.map((option) => (
                  <label
                    key={option.value}
                    className={`feedback-category${draft.category === option.value ? ' selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="feedback-category"
                      value={option.value}
                      checked={draft.category === option.value}
                      onChange={() => onDraftChange({ ...draft, category: option.value })}
                    />
                    <span className="feedback-category-label">{option.label}</span>
                    <span className="feedback-category-hint">{option.hint}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="feedback-field">
              <label className="feedback-label" htmlFor="feedback-message">
                Your feedback <span className="feedback-required">(required)</span>
              </label>
              <textarea
                id="feedback-message"
                ref={messageRef}
                className="feedback-textarea"
                value={draft.message}
                onChange={(event) => onDraftChange({ ...draft, message: event.target.value })}
                maxLength={MAX_MESSAGE_CHARS}
                rows={5}
                disabled={pending}
                required
                aria-describedby="feedback-message-hint"
                placeholder="Tell us what happened, or what you would like to see."
              />
              <div className="feedback-meta" id="feedback-message-hint">
                <span className="feedback-hint">Up to {MAX_MESSAGE_CHARS} characters.</span>
                <span className="feedback-counter" aria-live="polite">
                  {trimmed.length}/{MAX_MESSAGE_CHARS}
                </span>
              </div>
            </div>

            <label className="feedback-consent">
              <input
                type="checkbox"
                checked={draft.contactAllowed}
                onChange={(event) => onDraftChange({ ...draft, contactAllowed: event.target.checked })}
                disabled={pending}
              />
              <span>You can contact me about this feedback.</span>
            </label>

            <div className="feedback-actions">
              <button
                type="button"
                className="feedback-btn feedback-btn-ghost"
                onClick={handleClose}
              >
                {pending ? 'Close' : 'Cancel'}
              </button>
              <button
                type="submit"
                className="feedback-btn feedback-btn-primary"
                disabled={!canSubmit}
              >
                {pending ? 'Sending…' : 'Send feedback'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
