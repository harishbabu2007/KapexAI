import type { ComponentType } from 'react'
import { AstrologyCard } from './AstrologyCard'
import { MarkdownMessage } from './MarkdownMessage'
import { QuestionnaireCard } from './QuestionnaireCard'
import { QuestionnaireCompleteCard } from './QuestionnaireCompleteCard'
import { ResearchCard } from './ResearchCard'
import { SwotCard } from './SwotCard'
import type { MessageComponentProps } from './types'

/**
 * Registry of assistant-message renderers, keyed by the message `type` that the
 * worker emits (see `worker/tools/` — every tool owns its own message shape).
 *
 * Adding support for a NEW tool is a two-step, frontend-only change:
 *
 *   1. Create a component that takes `{ message: ChatMessage }`, e.g.
 *      `MyToolCard.tsx`, reading whatever extra fields your tool emits.
 *   2. Import it here and add an entry: `my_tool_type: MyToolCard`.
 *
 * Unknown types fall back to `MarkdownMessage`, so a tool without a frontend
 * component still degrades gracefully to a plain markdown reply.
 */
const registry: Record<string, ComponentType<MessageComponentProps>> = {
  chat: MarkdownMessage,
  questionnaire: QuestionnaireCard,
  questionnaire_complete: QuestionnaireCompleteCard,
  swot: SwotCard,
  research: ResearchCard,
  astrology: AstrologyCard,
}

export function MessageContent(props: MessageComponentProps) {
  const Component = registry[props.message.type] ?? MarkdownMessage
  return <Component {...props} />
}

export { registry }
