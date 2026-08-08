import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { MessageComponentProps } from './types'

export function ResearchCard({ message }: MessageComponentProps) {
  const content = message.content ?? ''
  return (
    <div className="tool-card research-card">
      <div className="tool-card-title">Market Research</div>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
