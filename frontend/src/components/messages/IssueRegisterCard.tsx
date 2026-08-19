import type { LegalIssue } from '../../lib/types'
import type { MessageComponentProps } from './types'

const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const BASIS_LABELS: Record<string, string> = {
  source: 'Grounded in a source',
  user_concern: 'Raised by you',
  inference: 'Inference',
}

/**
 * Renders a prioritized compliance issue register (`issue_register`). Each
 * issue shows its deterministic risk score, the basis for the finding, and the
 * retrieved source URLs it is grounded in.
 */
export function IssueRegisterCard({ message }: MessageComponentProps) {
  const issues = (message.issues ?? []) as LegalIssue[]
  const disclaimer = message.disclaimer as string | undefined

  return (
    <div className="tool-card legal-card issue-card">
      <div className="tool-card-title">Compliance issue register</div>

      <div className="issue-list">
        {issues.length === 0 ? (
          <p className="legal-empty">
            No compliance issues were identified from what we have so far.
          </p>
        ) : (
          issues.map((issue, index) => (
            <div className="issue-item" key={`${issue.title}-${index}`}>
              <div className="issue-item-head">
                <span className="issue-title">{issue.title}</span>
                <span className={`priority-badge priority-${issue.priority}`}>
                  {PRIORITY_LABELS[issue.priority] ?? issue.priority} · {issue.priority_score}
                </span>
              </div>

              <div className="issue-item-meta">
                {issue.category ? (
                  <span>
                    <b>Category:</b> {issue.category}
                  </span>
                ) : null}
                <span className={`basis-badge basis-${issue.basis}`}>
                  {BASIS_LABELS[issue.basis] ?? issue.basis}
                </span>
              </div>

              <p className="issue-explanation">{issue.explanation}</p>
              {issue.mitigation ? (
                <p className="issue-mitigation">
                  <b>Suggested action:</b> {issue.mitigation}
                </p>
              ) : null}

              {issue.grounded_in.length > 0 ? (
                <ul className="issue-sources">
                  {issue.grounded_in.map((url) => (
                    <li key={url}>
                      <a href={url} target="_blank" rel="noreferrer">
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))
        )}
      </div>

      {disclaimer ? <p className="legal-disclaimer">{disclaimer}</p> : null}
    </div>
  )
}