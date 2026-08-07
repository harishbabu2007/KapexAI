import { Markdown } from '../../lib/markdown'
import type { MessageComponentProps } from './types'

/**
 * Default renderer for plain assistant messages (e.g. the chat agent's reply)
 * and any unknown tool type. Renders `content` as markdown.
 */
export function MarkdownMessage({ message }: MessageComponentProps) {
  return <Markdown>{message.content ?? ''}</Markdown>
}
