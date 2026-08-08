import type { QuestionnaireState } from '../../lib/types'
import type { MessageComponentProps } from './types'

export function QuestionnaireCard({ message }: MessageComponentProps) {
  const q = message.questionnaire as QuestionnaireState | undefined
  const questions = q?.questions ?? []
  const answers = q?.answers ?? []

  return (
    <div className="tool-card questionnaire-card">
      <div className="tool-card-title">Business Questionnaire</div>
      <ol className="questionnaire-list">
        {questions.map((question, i) => {
          const answered = answers[i] !== undefined
          return (
            <li key={i} className={answered ? 'q-item answered' : 'q-item pending'}>
              <span className="q-number">{i + 1}</span>
              <div className="q-body">
                <p className="q-text">{question}</p>
                {answered && <p className="q-answer">↳ {answers[i]}</p>}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
