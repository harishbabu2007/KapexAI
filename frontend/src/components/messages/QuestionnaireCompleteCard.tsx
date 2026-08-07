import type { MessageComponentProps } from './types'

function label(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Confirmation card rendered when the questionnaire is complete (message type
 * `questionnaire_complete`). Displays the collected business context.
 */
export function QuestionnaireCompleteCard({ message }: MessageComponentProps) {
  const context = (message.context ?? {}) as Record<string, string>
  const entries = Object.entries(context).filter(([, value]) => value)

  return (
    <div className="tool-card questionnaire-complete-card">
      <div className="tool-card-title">Questionnaire complete</div>
      <p>{message.content}</p>
      {entries.length > 0 && (
        <dl className="context-list">
          {entries.map(([key, value]) => (
            <div className="context-row" key={key}>
              <dt>{label(key)}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
