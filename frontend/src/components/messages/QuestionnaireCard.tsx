import type { QuestionnaireQuestion } from '../../lib/types'
import type { MessageComponentProps } from './types'

/**
 * Renders the questionnaire tool's questions (assistant message of type
 * `questionnaire`). The user answers all of them in a single reply.
 */
export function QuestionnaireCard({ message }: MessageComponentProps) {
  const questions = (message.questions ?? []) as QuestionnaireQuestion[]

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
    </div>
  )
}
