import type { MessageComponentProps } from './types'

const ACRONYMS = new Set([
  'apy',
  'elss',
  'emi',
  'epf',
  'hra',
  'mis',
  'nps',
  'ppf',
  'rd',
  'sip',
  'ssy',
  'tds',
])

const RATE_KEY = /(rate|return|percentage)/i
const COUNT_KEY = /(years?|months?|age|term|period|depleted)/i
const CAUTION_KEY = 'caution'

function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** `sip_calculator` → "SIP Calculator", `nps_india_calculator` → "NPS India Calculator". */
function calculatorName(type: string): string {
  const base = type.replace(/_calculator$/, '').split('_')
  const title = base
    .map((token) =>
      ACRONYMS.has(token) ? token.toUpperCase() : token.charAt(0).toUpperCase() + token.slice(1),
    )
    .join(' ')
  return title ? `${title} Calculator` : 'Finance Calculator'
}

/** Parse the worker's `content`: summary line → result bullets → explanation. */
function parseContent(content: string): { summary: string; explanation: string } {
  const lines = content.split('\n')
  let i = 0
  while (i < lines.length && !lines[i].trim()) i++
  const summary = i < lines.length ? lines[i].trim() : ''
  while (i < lines.length && lines[i].startsWith('- ')) i++
  const explanation = lines
    .slice(i)
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n')
  return { summary, explanation }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    if (RATE_KEY.test(key)) {
      return `${(value * 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}%`
    }
    if (COUNT_KEY.test(key)) {
      return value.toLocaleString('en-IN')
    }
    return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
  }
  return String(value)
}

function NestedRows({ obj }: { obj: Record<string, unknown> }) {
  return (
    <div className="finance-nested">
      {Object.entries(obj).map(([key, value]) => (
        <div className="finance-row" key={key}>
          <dt>{humanize(key)}</dt>
          <dd>{isRecord(value) ? <NestedRows obj={value} /> : formatValue(key, value)}</dd>
        </div>
      ))}
    </div>
  )
}

/**
 * Renders an Indian finance calculation (assistant message of type
 * `indian_finance`) as a structured result card: humanized calculator name,
 * the summary line, key/value rows for the calculator output (rates as
 * percentages, money in ₹ with Indian digit grouping), the `caution` note, and
 * the plain-English explanation.
 */
export function IndianFinanceCard({ message }: MessageComponentProps) {
  const calculationType = (message.calculation_type as string) ?? ''
  const rawResult = (message.result ?? {}) as Record<string, unknown>
  const { summary, explanation } = parseContent(message.content ?? '')

  const caution = typeof rawResult[CAUTION_KEY] === 'string' ? rawResult[CAUTION_KEY] : undefined
  const result = Object.entries(rawResult).filter(([key]) => key !== CAUTION_KEY)

  return (
    <div className="tool-card indian-finance-card">
      <div className="tool-card-title">Indian finance calculator</div>
      <div className="finance-type">{calculatorName(calculationType)}</div>
      {summary ? <p className="finance-summary">{summary}</p> : null}
      {result.length > 0 && (
        <dl className="finance-result">
          {result.map(([key, value]) => (
            <div className="finance-row" key={key}>
              <dt>{humanize(key)}</dt>
              <dd>{isRecord(value) ? <NestedRows obj={value} /> : formatValue(key, value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {caution ? <p className="finance-caution">{caution}</p> : null}
      {explanation ? <p className="finance-explanation">{explanation}</p> : null}
    </div>
  )
}