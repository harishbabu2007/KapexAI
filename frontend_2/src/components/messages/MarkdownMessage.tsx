import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { MessageComponentProps } from './types'

export function MarkdownMessage({ message }: MessageComponentProps) {
  const content = message.content ?? ''
  return (
    <div className="tool-card markdown-card">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
