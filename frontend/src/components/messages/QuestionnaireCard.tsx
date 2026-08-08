import { useState } from 'react'
import type {
  QuestionnaireAnswer,
  QuestionnaireQuestion,
} from '../../lib/types'
import type { MessageComponentProps } from './types'

/**
 * Claude-style slide questionnaire (assistant message of type `questionnaire`).
 *
 * One question is shown at a time; the user answers and clicks Next to advance,
 * Back to correct an earlier answer, and Submit on the last slide. All answers
 * are collected and sent to the backend in one structured request.
 */
export function QuestionnaireCard({
  message,
  streaming,
  completed,
  onSubmitQuestionnaire,
  onClarifyQuestion,
}: MessageComponentProps) {
  const questions = (message.questions ?? []) as QuestionnaireQuestion[]
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  if (completed) {
    return (
      <div className="tool-card questionnaire-card">
        <div className="tool-card-title">Business questionnaire</div>
        <p>{message.content}</p>
        {questions.length > 0 && (
          <ol className="questionnaire-questions">
            {questions.map((q) => (
              <li key={q.key ?? q.question}>{q.question}</li>
            ))}
          </ol>
        )}
        <p className="questionnaire-done">Completed — see the summary above.</p>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="tool-card questionnaire-card">
        <div className="tool-card-title">Business questionnaire</div>
        <p>{message.content}</p>
      </div>
    )
  }

  const current = questions[index]
  const isLast = index === questions.length - 1
  const answeredCount = questions.filter(
    (q) => (answers[q.key] ?? '').trim().length > 0,
  ).length
  const canSubmit = answeredCount > 0
  const locked = Boolean(streaming)

  function handleSubmit() {
    if (!canSubmit || locked) return
    const payload: QuestionnaireAnswer[] = questions.map((q) => ({
      key: q.key,
      answer: (answers[q.key] ?? '').trim(),
    }))
    onSubmitQuestionnaire?.(payload)
  }

  return (
    <div className="tool-card questionnaire-card">
      <div className="tool-card-title">Business questionnaire</div>
      <p className="questionnaire-intro">{message.content}</p>

      <div className="questionnaire-slide">
        <div className="questionnaire-slide-meta">
          <span>
            Question {index + 1} of {questions.length}
          </span>
          <span className="questionnaire-answered">
            {answeredCount} answered
          </span>
        </div>

        <div className="questionnaire-dots" aria-hidden="true">
          {questions.map((q, i) => (
            <button
              type="button"
              key={q.key}
              className={`questionnaire-dot${i === index ? ' current' : ''}${
                (answers[q.key] ?? '').trim() ? ' filled' : ''
              }`}
              onClick={() => setIndex(i)}
              disabled={locked}
              aria-label={`Go to question ${i + 1}`}
            />
          ))}
        </div>

        <h4 className="questionnaire-slide-question">{current.question}</h4>

        {onClarifyQuestion && (
          <button
            type="button"
            className="qn-clarify"
            onClick={() =>
              onClarifyQuestion(
                [current.key],
                `Could you explain this in simpler words? ${current.question}`,
              )
            }
            disabled={locked}
          >
            Explain in simpler words
          </button>
        )}

        <textarea
          className="questionnaire-slide-input"
          value={answers[current.key] ?? ''}
          onChange={(event) =>
            setAnswers((prev) => ({ ...prev, [current.key]: event.target.value }))
          }
          rows={3}
          disabled={locked}
          placeholder="Type your answer…"
          autoFocus
          aria-label="Your answer"
        />

        <div className="questionnaire-slide-nav">
          <button
            type="button"
            className="qn-btn qn-back"
            onClick={() => setIndex((i) => i - 1)}
            disabled={index === 0 || locked}
          >
            Back
          </button>

          {isLast ? (
            <button
              type="button"
              className="send-btn qn-submit"
              onClick={handleSubmit}
              disabled={!canSubmit || locked}
            >
              Submit answers
            </button>
          ) : (
            <button
              type="button"
              className="send-btn qn-next"
              onClick={() => setIndex((i) => i + 1)}
              disabled={locked}
            >
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
