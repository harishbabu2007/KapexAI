/**
 * Feedback submission lifecycle.
 *
 * Extracted from `ChatPage` so the pending/settle rules are testable without a
 * DOM, and so they cannot be bypassed by accident. The rules it encodes:
 *
 * 1. **One request at a time.** A second `submit()` while one is in flight is
 *    ignored outright, not queued and not coalesced.
 * 2. **Closing the dialog does not touch any of this.** There is deliberately no
 *    `close`/`cancel` method here. Hiding the dialog is a UI concern; the request
 *    keeps running and its outcome is still recorded. (A previous version
 *    aborted and cleared the pending flag on close, which both lost the outcome
 *    and let a reopened dialog immediately send a second row.)
 * 3. **Only the owning request's completion may publish state.** Each request
 *    takes a sequence number; a completion whose number is stale is dropped, so
 *    a late reply can never overwrite a newer outcome.
 * 4. **An abort is not proof of a non-write.** `abort()` exists for unmount
 *    cleanup only. If a request is aborted anyway, the result is reported as
 *    `uncertain`, because nothing in the client can establish whether the
 *    backend appended a row.
 *
 * There are no runtime imports: `send` and `describeError` are injected, so this
 * module can be exercised with fakes that never touch the network.
 */

import type { FeedbackFailure } from './api'

export type FeedbackResult =
  | { phase: 'pending' }
  | { phase: 'delivered'; feedbackId: string }
  | { phase: 'failed'; failure: FeedbackFailure }

export type FeedbackLifecycleDeps<P> = {
  /** Performs the request. Injected so tests never reach the network. */
  send: (payload: P, signal: AbortSignal) => Promise<{ feedback_id: string }>
  /** Normalises a rejection into the shape the dialog renders. */
  describeError: (err: unknown) => FeedbackFailure
  /** Called on every state transition, including the initial pending state. */
  onChange: (result: FeedbackResult) => void
}

/** An abort tells us nothing about whether a row was written. */
function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    (err as { name?: string }).name === 'AbortError'
  )
}

const ABORTED: FeedbackFailure = {
  message: 'The request was cancelled before we could confirm the outcome.',
  code: 'request_aborted',
  delivery: 'uncertain',
  feedbackId: null,
  retryAfterSeconds: null,
}

export type FeedbackLifecycle<P> = {
  /** Sends the feedback. Resolves once the outcome has been published. */
  submit: (payload: P) => Promise<void>
  /** Unmount cleanup only. Never call this to cancel a user's submission. */
  abort: () => void
  /** True while a request is on the wire. */
  isPending: () => boolean
}

export function createFeedbackLifecycle<P>(
  deps: FeedbackLifecycleDeps<P>,
): FeedbackLifecycle<P> {
  let inFlight = false
  let seq = 0
  let controller: AbortController | null = null

  async function submit(payload: P): Promise<void> {
    // Rule 1. Returning here is what makes a duplicate row impossible, and it
    // stays correct across a dialog close because close cannot reach this.
    if (inFlight) return
    inFlight = true
    const mySeq = ++seq
    controller = new AbortController()
    deps.onChange({ phase: 'pending' })

    try {
      const response = await deps.send(payload, controller.signal)
      if (mySeq !== seq) return
      deps.onChange({ phase: 'delivered', feedbackId: response.feedback_id })
    } catch (err) {
      if (mySeq !== seq) return
      // Rule 4: an abort is reported as uncertain, never as a clean failure.
      deps.onChange({
        phase: 'failed',
        failure: isAbortError(err) ? { ...ABORTED } : deps.describeError(err),
      })
    } finally {
      // Rule 3. Only this request's own completion clears the pending state.
      if (mySeq === seq) {
        inFlight = false
        controller = null
      }
    }
  }

  function abort(): void {
    controller?.abort()
  }

  return { submit, abort, isPending: () => inFlight }
}
