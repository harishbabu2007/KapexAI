import type { IndianCase } from '../../lib/types'
import type { MessageComponentProps } from './types'

/**
 * Renders an Indian case-law search (`case_search`) sourced from Indian Kanoon.
 * The database is a third-party legal source and is labelled as such; the
 * tool never presents it as an official court record.
 */
export function CaseSearchCard({ message }: MessageComponentProps) {
  const cases = (message.cases ?? []) as IndianCase[]
  const disclaimer = message.disclaimer as string | undefined
  const query = message.query as string | undefined

  return (
    <div className="tool-card legal-card case-card">
      <div className="tool-card-title">
        Indian case search
        <span className="source-badge source-third_party">Third-party database</span>
      </div>
      {query ? <p className="legal-query">Query: {query}</p> : null}

      <div className="legal-result-list">
        {cases.length === 0 ? (
          <p className="legal-empty">No cases matched. Try rephrasing the query.</p>
        ) : (
          cases.map((case_, index) => (
            <div className="legal-result" key={`${case_.url}-${index}`}>
              <div className="legal-result-head">
                {case_.url ? (
                  <a href={case_.url} target="_blank" rel="noreferrer">
                    {case_.case_name || case_.url}
                  </a>
                ) : (
                  <span>{case_.case_name || 'Untitled judgment'}</span>
                )}
              </div>

              <div className="legal-result-meta">
                {case_.court ? (
                  <span>
                    <b>Court:</b> {case_.court}
                  </span>
                ) : null}
                {case_.date ? (
                  <span>
                    <b>Decided:</b> {case_.date}
                  </span>
                ) : null}
                {case_.relevance ? <span>{case_.relevance}</span> : null}
              </div>

              {case_.summary ? <p className="legal-result-summary">{case_.summary}</p> : null}
            </div>
          ))
        )}
      </div>

      {disclaimer ? <p className="legal-disclaimer">{disclaimer}</p> : null}
    </div>
  )
}