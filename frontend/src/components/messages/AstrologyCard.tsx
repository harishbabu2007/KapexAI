import { Markdown } from '../../lib/markdown'
import type { MessageComponentProps } from './types'

/**
 * Renders a symbolic astrology reading (assistant message of type `astrology`).
 * The agent's answer is free-form markdown; the disclaimer is rendered as a
 * distinct footer so the non-scientific nature stays visibly separated.
 */
export function AstrologyCard({ message }: MessageComponentProps) {
  const disclaimer = message.disclaimer as string | undefined

  return (
    <div className="tool-card astrology-card">
      <div className="tool-card-title">Symbolic astrology</div>
      <Markdown>{message.content ?? ''}</Markdown>
      {disclaimer ? (
        <div className="astrology-disclaimer">{disclaimer}</div>
      ) : null}
    </div>
  )
}