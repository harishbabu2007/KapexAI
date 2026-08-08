export interface ToolDefinition {
  id: string
  title: string
  category: 'Strategy' | 'Finance' | 'Research' | 'Operations' | 'Growth'
  description: string
  iconName: string
  x: number // canvas coordinates
  y: number
  badge?: string
}

export const TOOLS_DATA: ToolDefinition[] = [
  {
    id: 'swot',
    title: 'SWOT & Competitive Matrix',
    category: 'Strategy',
    description: 'Deep AI-driven market positioning and threat analysis.',
    iconName: 'ShieldAlert',
    x: -320,
    y: -220,
    badge: 'Core'
  },
  {
    id: 'financial',
    title: 'Financial Projections & Unit Economics',
    category: 'Finance',
    description: '3-year P&L, DCF valuation, and cash burn forecasting.',
    iconName: 'TrendingUp',
    x: 340,
    y: -200,
    badge: 'Popular'
  },
  {
    id: 'market',
    title: 'TAM/SAM/SOM Market Research',
    category: 'Research',
    description: 'Real-time industry sizing, tailwinds, and competitor benchmarking.',
    iconName: 'Globe',
    x: -380,
    y: 180,
    badge: 'Live Data'
  },
  {
    id: 'strategy',
    title: 'Executive GTM Blueprint',
    category: 'Growth',
    description: 'B2B/B2C go-to-market playbook with pricing psychology.',
    iconName: 'Compass',
    x: 380,
    y: 190,
    badge: 'McKinsey Grade'
  },
  {
    id: 'risk',
    title: 'Regulatory & Risk Mitigation',
    category: 'Operations',
    description: 'Compliance scanning, legal bottleneck identification, & mitigation.',
    iconName: 'Lock',
    x: 0,
    y: -340,
  },
  {
    id: 'pitch',
    title: 'Investor Deck Generator',
    category: 'Finance',
    description: '12-slide institutional pitch deck structured for tier-1 VCs.',
    iconName: 'Layers',
    x: 0,
    y: 320,
    badge: 'AI PPTX'
  }
]
