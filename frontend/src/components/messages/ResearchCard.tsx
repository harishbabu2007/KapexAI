import { Markdown } from '../../lib/markdown'
import type { MessageComponentProps } from './types'

/**
 * Renders a live web-research result (assistant message of type `research`).
 * The agent's answer is free-form markdown, so it renders like a chat reply
 * but inside a labelled research card.
 */
export function ResearchCard({ message }: MessageComponentProps) {
  return (
    <div className="tool-card research-card">
      <div className="tool-card-title">Live research</div>
      <Markdown>{message.content ?? ''}</Markdown>
    </div>
  )
}
