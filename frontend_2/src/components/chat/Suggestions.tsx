import type { ToolInfo } from '../../lib/types'

interface SuggestionsProps {
  suggestions: ToolInfo[]
  onPick: (tool: ToolInfo) => void
}

export function Suggestions({ suggestions, onPick }: SuggestionsProps) {
  if (suggestions.length === 0) return null

  return (
    <div className="suggestions-container">
      <span className="suggestions-label">Suggested next steps:</span>
      <div className="suggestions-chips">
        {suggestions.map((s, idx) => (
          <button key={idx} type="button" className="suggestion-chip" onClick={() => onPick(s)}>
            <span className="chip-title">{s.title}</span>
            <span className="chip-example">&ldquo;{s.example}&rdquo;</span>
          </button>
        ))}
      </div>
    </div>
  )
}
