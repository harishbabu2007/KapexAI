import type { ToolInfo } from '../../lib/types'

type SuggestionsProps = {
  suggestions: ToolInfo[]
  onPick: (tool: ToolInfo) => void
}

/** "Wanna try this next?" chips suggested by the assistant after a turn. */
export function Suggestions({ suggestions, onPick }: SuggestionsProps) {
  return (
    <div className="suggestions">
      <span className="suggestions-label">Try:</span>
      {suggestions.map((tool) => (
        <button
          key={tool.name}
          type="button"
          className="suggestion-chip"
          onClick={() => onPick(tool)}
          title={tool.example}
        >
          {tool.suggestion || tool.example}
        </button>
      ))}
    </div>
  )
}
