import type { MessageComponentProps } from './types'

export function SwotCard({ message }: MessageComponentProps) {
  const sections = message.sections ?? { strengths: [], weaknesses: [], opportunities: [], threats: [] }

  return (
    <div className="tool-card swot-card">
      <div className="tool-card-title">SWOT Analysis</div>
      {message.summary && <p className="swot-summary">{message.summary}</p>}

      <div className="swot-grid">
        <div className="swot-section strengths">
          <h4>Strengths</h4>
          <ul>
            {sections.strengths.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="swot-section weaknesses">
          <h4>Weaknesses</h4>
          <ul>
            {sections.weaknesses.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="swot-section opportunities">
          <h4>Opportunities</h4>
          <ul>
            {sections.opportunities.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="swot-section threats">
          <h4>Threats</h4>
          <ul>
            {sections.threats.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
