import type { SwotSections } from '../../lib/types'
import type { MessageComponentProps } from './types'

const SECTION_LABELS: Array<[keyof SwotSections, string]> = [
  ['strengths', 'Strengths'],
  ['weaknesses', 'Weaknesses'],
  ['opportunities', 'Opportunities'],
  ['threats', 'Threats'],
]

/**
 * Renders a SWOT analysis (assistant message of type `swot`) as a four-cell
 * grid using the structured `sections` payload.
 */
export function SwotCard({ message }: MessageComponentProps) {
  const sections = (message.sections ?? {}) as Partial<SwotSections>
  const summary = message.summary as string | undefined

  return (
    <div className="tool-card swot-card">
      <div className="tool-card-title">SWOT analysis</div>
      {summary ? <p className="swot-summary">{summary}</p> : null}
      <div className="swot-grid">
        {SECTION_LABELS.map(([key, label]) => (
          <div className={`swot-section swot-${key}`} key={key}>
            <h4>{label}</h4>
            <ul>
              {(sections[key] ?? []).map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}
