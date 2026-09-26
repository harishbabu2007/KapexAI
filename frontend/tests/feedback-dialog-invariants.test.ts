/**
 * Source-level invariants for the feedback dialog.
 *
 * The close/reopen bug this guards against lived in `ChatPage`, in the
 * `closeFeedback` callback, not in the lifecycle module. Without a DOM or a
 * test framework we cannot mount `ChatPage`, so these assertions read the
 * component sources and pin the properties that matter:
 *
 *  - closing the dialog must not abort the request
 *  - closing the dialog must not clear the outcome
 *  - the old abort-on-close props must stay gone
 *
 * These fail loudly if someone reintroduces the original behaviour.
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

const chatPage = read('../src/pages/ChatPage.tsx')
const dialog = read('../src/components/feedback/FeedbackDialog.tsx')

/** Returns the source of `const <name> = useCallback(...)` including its body. */
function callbackBody(src: string, name: string): string {
  const start = src.indexOf(`const ${name} = useCallback(`)
  assert.notEqual(start, -1, `expected a useCallback named ${name}`)
  // Walk forward balancing parens to the one that closes `useCallback(`.
  let depth = 0
  let i = src.indexOf('(', start)
  for (; i < src.length; i += 1) {
    const ch = src[i]
    if (ch === '(') depth += 1
    else if (ch === ')') {
      depth -= 1
      if (depth === 0) break
    }
  }
  assert.notEqual(i, src.length, `expected ${name} to close`)
  return src.slice(start, i + 1)
}

test('closeFeedback only hides the dialog', () => {
  const body = callbackBody(chatPage, 'closeFeedback')
  assert.match(body, /setFeedbackOpen\(false\)/)
  assert.doesNotMatch(
    body,
    /abort/i,
    'closing must not abort the request: an aborted fetch proves nothing about ' +
      'whether a row was written, and it would lose the outcome',
  )
  assert.doesNotMatch(
    body,
    /setFeedbackResult/,
    'closing must not clear the outcome; a reopened dialog has to show it',
  )
  assert.doesNotMatch(
    body,
    /setFeedbackDraft/,
    'closing must not discard the typed values',
  )
})

test('openFeedback only reveals the dialog', () => {
  const body = callbackBody(chatPage, 'openFeedback')
  assert.match(body, /setFeedbackOpen\(true\)/)
  assert.doesNotMatch(body, /setFeedbackResult|reset|abort/i)
})

test('resetFeedback is the only thing that clears the draft or result', () => {
  const body = callbackBody(chatPage, 'resetFeedback')
  assert.match(body, /setFeedbackDraft\(EMPTY_DRAFT\)/)
  assert.match(body, /setFeedbackResult\(null\)/)
  // Nothing else in the component may clear the result.
  const clears = chatPage.match(/setFeedbackResult\(null\)/g) ?? []
  assert.equal(clears.length, 1, 'only resetFeedback may clear the result')
})

test('the abort-on-close props are gone', () => {
  for (const src of [chatPage, dialog]) {
    assert.doesNotMatch(src, /requestInFlight|beginRequest|endRequest/)
  }
  // The dialog must not be handed a way to end a request.
  const props = dialog.slice(dialog.indexOf('type FeedbackDialogProps'))
  assert.doesNotMatch(props, /abort/i)
})

test('the dialog is told to close, and only to close', () => {
  assert.match(chatPage, /onClose=\{closeFeedback\}/)
  // onReset (a deliberate "new message") is separate from onClose.
  assert.match(chatPage, /onReset=\{resetFeedback\}/)
})

test('the pending state is driven by the parent result', () => {
  assert.match(dialog, /const pending = result\?\.phase === 'pending'/)
  // The dialog holds no request state of its own.
  assert.doesNotMatch(dialog, /useState/)
})
