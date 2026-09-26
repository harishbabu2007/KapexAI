/**
 * Feedback submission lifecycle tests.
 *
 * These run on Node's built-in test runner (`node --test` with
 * `--experimental-strip-types`), so there is no test framework to install.
 *
 * `send` is a fake. It never opens a socket, so nothing here can reach
 * `/feedback` or write a Google Sheets row; the close/reopen behaviour is
 * exercised purely against the injected fake.
 *
 * Run: npm test
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createFeedbackLifecycle } from '../src/lib/feedbackLifecycle.ts'
import type { FeedbackResult } from '../src/lib/feedbackLifecycle.ts'

/** A promise the test resolves or rejects by hand, to control timing exactly. */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** An error shaped like the one `fetch` throws when a signal is aborted. */
function abortError() {
  const err = new Error('The operation was aborted.')
  err.name = 'AbortError'
  return err
}

/**
 * A stand-in for ChatPage's ownership of the draft + result. Mirrors the real
 * component: the dialog mounting/unmounting only reads and writes these two
 * values, and never touches the lifecycle.
 */
function harness() {
  const states: FeedbackResult[] = []
  let current: FeedbackResult | null = null
  let draft = 'typed message'
  const sent: { message: string; signal: AbortSignal }[] = []
  const described: unknown[] = []
  // One fresh deferred per send, so each call can be settled independently.
  const inFlightRequests: ReturnType<typeof deferred<{ feedback_id: string }>>[] = []

  const lifecycle = createFeedbackLifecycle<{ message: string }>({
    send: (payload, signal) => {
      sent.push({ message: payload.message, signal })
      const d = deferred<{ feedback_id: string }>()
      inFlightRequests.push(d)
      return d.promise
    },
    describeError: (err) => {
      described.push(err)
      return {
        message: 'Something went wrong.',
        code: 'network_error',
        delivery: 'failed',
        feedbackId: null,
        retryAfterSeconds: 3,
      }
    },
    onChange: (next) => {
      current = next
      states.push(next)
    },
  })

  /** The most recent request the fake is holding open. */
  const req = () => {
    const d = inFlightRequests[inFlightRequests.length - 1]
    assert.ok(d, 'expected a request to have been sent')
    return d
  }

  return {
    lifecycle,
    states,
    sent,
    described,
    req,
    get result() {
      return current
    },
    get draft() {
      return draft
    },
    // Mount / unmount the dialog. Deliberately does nothing else: this is the
    // whole point of the fix, so it must be a no-op on the request.
    openDialog: () => draft,
    closeDialog: () => {
      /* only hides the dialog */
    },
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

test('a submit publishes pending and keeps the request running', async () => {
  const h = harness()
  const done = h.lifecycle.submit({ message: h.draft })
  await flush()

  assert.equal(h.result?.phase, 'pending')
  assert.equal(h.lifecycle.isPending(), true)
  assert.equal(h.sent.length, 1)

  h.req().resolve({ feedback_id: 'fb_1' })
  await done
  assert.equal(h.result?.phase, 'delivered')
  assert.equal(h.lifecycle.isPending(), false)
})

test('closing and reopening the dialog mid-flight cannot cause a second row', async () => {
  const h = harness()
  const first = h.lifecycle.submit({ message: h.draft })
  await flush()

  // Cycle the dialog several times while the request is still on the wire. A
  // reopened form would offer Send again if closing had cleared pending state.
  for (let i = 0; i < 3; i += 1) {
    h.openDialog()
    h.closeDialog()
    // A click on a form that wrongly offers Send would reach the network here.
    void h.lifecycle.submit({ message: h.draft })
  }
  await flush()

  assert.equal(h.sent.length, 1, 'only one request may ever be sent')
  assert.equal(h.lifecycle.isPending(), true, 'closing must not clear pending')
  assert.equal(h.result?.phase, 'pending', 'reopening must still show pending')

  h.req().resolve({ feedback_id: 'fb_2' })
  await first
  assert.equal(h.result?.phase, 'delivered')
})

test('closing the dialog does not abort the request', async () => {
  const h = harness()
  const done = h.lifecycle.submit({ message: h.draft })
  await flush()

  h.openDialog()
  h.closeDialog()
  h.openDialog()
  await flush()

  assert.equal(h.sent[0].signal.aborted, false, 'close must not abort the signal')

  h.req().resolve({ feedback_id: 'fb_3' })
  await done
  assert.equal(h.result?.phase, 'delivered', 'the outcome is still delivered')
})

test('a success after a close is preserved and shows the reference id', async () => {
  const h = harness()
  const done = h.lifecycle.submit({ message: h.draft })
  await flush()
  h.closeDialog()
  h.openDialog()

  h.req().resolve({ feedback_id: 'fb_abc' })
  await done

  assert.deepEqual(h.result, { phase: 'delivered', feedbackId: 'fb_abc' })
  // The typed values are the parent's, so a reopened dialog still shows them.
  assert.equal(h.draft, 'typed message')
})

test('a failure after a close is preserved, with its code', async () => {
  const h = harness()
  const done = h.lifecycle.submit({ message: h.draft })
  await flush()
  h.closeDialog()

  h.req().reject(new Error('HTTP 503'))
  await done

  assert.equal(h.result?.phase, 'failed')
  const failure = h.result?.phase === 'failed' ? h.result.failure : null
  assert.equal(failure?.code, 'network_error')
  assert.equal(h.described.length, 1, 'non-abort errors are described')
  assert.equal(h.lifecycle.isPending(), false)
})

test('an abort is reported as uncertain, never as a confirmed failure', async () => {
  const h = harness()
  const done = h.lifecycle.submit({ message: h.draft })
  await flush()

  // Unmount cleanup.
  h.lifecycle.abort()
  h.req().reject(abortError())
  await done

  const failure = h.result?.phase === 'failed' ? h.result.failure : null
  assert.equal(failure?.delivery, 'uncertain')
  assert.equal(failure?.code, 'request_aborted')
  assert.equal(failure?.feedbackId, null)
  // An abort must not be laundered through the normal error path.
  assert.equal(h.described.length, 0)
  assert.equal(h.lifecycle.isPending(), false)
})

test('a new submission is allowed only after the previous one settles', async () => {
  const h = harness()
  const first = h.lifecycle.submit({ message: h.draft })
  await flush()
  h.req().resolve({ feedback_id: 'fb_1' })
  await first
  assert.equal(h.lifecycle.isPending(), false)

  const second = h.lifecycle.submit({ message: 'second message' })
  await flush()
  assert.equal(h.sent.length, 2)
  assert.equal(h.sent[1].message, 'second message')

  h.req().resolve({ feedback_id: 'fb_4' })
  await second
  assert.deepEqual(h.result, { phase: 'delivered', feedbackId: 'fb_4' })
})

test('each submission uses a fresh, un-aborted signal', async () => {
  const h = harness()
  const first = h.lifecycle.submit({ message: h.draft })
  await flush()
  h.lifecycle.abort() // e.g. unmount mid-flight
  h.req().reject(abortError())
  await first

  const second = h.lifecycle.submit({ message: 'after abort' })
  await flush()
  assert.equal(h.sent[1].signal.aborted, false, 'a new request is not pre-aborted')
  assert.notEqual(h.sent[0].signal, h.sent[1].signal)

  h.req().resolve({ feedback_id: 'fb_5' })
  await second
})

test('the lifecycle exposes no way to cancel a submission', () => {
  // Compile-time plus runtime guard: the only teardown method is `abort`, which
  // is documented as unmount cleanup, and there is no `close`/`cancel` that a
  // dialog dismiss could reach.
  const h = harness()
  assert.deepEqual(
    Object.keys(h.lifecycle).sort(),
    ['abort', 'isPending', 'submit'].sort(),
  )
})
