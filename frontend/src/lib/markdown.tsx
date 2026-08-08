import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Renders assistant message content, which is markdown (GFM tables, lists, bold, etc.). */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}
