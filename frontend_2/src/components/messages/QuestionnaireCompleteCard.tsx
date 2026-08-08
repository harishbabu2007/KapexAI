import type { MessageComponentProps } from './types'

export function QuestionnaireCompleteCard({ message }: MessageComponentProps) {
  return (
    <div className="tool-card questionnaire-complete">
      <div className="tool-card-title">Questionnaire Complete</div>
      <p>{message.content ?? 'All business context questions have been answered.'}</p>
    </div>
  )
}
