import type { LegalResearchResult } from '../../lib/types'
import type { MessageComponentProps } from './types'

const SOURCE_LABELS: Record<string, string> = {
  official: 'Official source',
  third_party: 'Third-party source',
}

/**
 * Renders a regulatory search (`legal_research`) as a list of results, each
 * labelled official (centralized domain allowlist) or third-party, with the
 * source-driving fields surfaced (authority, document type, jurisdiction,
 * dates, sections, citation) alongside a plain-language summary.
 */
export function LegalResearchCard({ message }: MessageComponentProps) {
  const results = (message.results ?? []) as LegalResearchResult[]
  const disclaimer = message.disclaimer as string | undefined
  const query = message.query as string | undefined

  return (
    <div className="tool-card legal-card">
      <div className="tool-card-title">Indian regulatory search</div>
      {query ? <p className="legal-query">Query: {query}</p> : null}

      <div className="legal-result-list">
        {results.length === 0 ? (
          <p className="legal-empty">No relevant official sources found. Try rephrasing.</p>
        ) : (
          results.map((result, index) => (
            <div className="legal-result" key={`${result.source_url}-${index}`}>
              <div className="legal-result-head">
                {result.source_url ? (
                  <a href={result.source_url} target="_blank" rel="noreferrer">
                    {result.title || result.source_url}
                  </a>
                ) : (
                  <span>{result.title || 'Untitled source'}</span>
                )}
                <span className={`source-badge source-${result.source_type}`}>
                  {SOURCE_LABELS[result.source_type] ?? result.source_type}
                </span>
              </div>

              <div className="legal-result-meta">
                {result.authority ? (
                  <span>
                    <b>Authority:</b> {result.authority}
                  </span>
                ) : null}
                {result.document_type ? (
                  <span>
                    <b>Type:</b> {result.document_type}
                  </span>
                ) : null}
                {result.jurisdiction ? (
                  <span>
                    <b>Jurisdiction:</b> {result.jurisdiction}
                  </span>
                ) : null}
                {result.publication_date ? (
                  <span>
                    <b>Published:</b> {result.publication_date}
                  </span>
                ) : null}
                {result.effective_date ? (
                  <span>
                    <b>In effect from:</b> {result.effective_date}
                  </span>
                ) : null}
              </div>

              {result.summary ? <p className="legal-result-summary">{result.summary}</p> : null}
              {result.relevant_sections.length > 0 ? (
                <p className="legal-result-sections">
                  <b>Sections:</b> {result.relevant_sections.join(', ')}
                </p>
              ) : null}
              {result.citation ? (
                <p className="legal-result-citation">
                  <b>Citation:</b> {result.citation}
                </p>
              ) : null}
            </div>
          ))
        )}
      </div>

      {disclaimer ? <p className="legal-disclaimer">{disclaimer}</p> : null}
    </div>
  )
}