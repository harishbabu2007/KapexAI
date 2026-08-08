import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ArrowDown, ArrowUpRight, Compass, LockKeyhole, Network, Sparkles, X } from 'lucide-react'
import { type CSSProperties, type PointerEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GoogleSignInButton } from '../components/auth/GoogleSignInButton'
import { TOOLS_DATA, type ToolDefinition } from '../constants/tools'
import { useAuth } from '../lib/auth'
import '../styles/canvas-landing.css'

const iconFor = (name: string) => name === 'Lock' ? LockKeyhole : name === 'Compass' ? Compass : Network

export function CanvasLandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()
  const reduceMotion = useReducedMotion()
  const [freeRoam, setFreeRoam] = useState(false)
  const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null)

  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === 'Escape' && setSelectedTool(null)
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    if (!freeRoam || (event.target as HTMLElement).closest('button, .tool-island')) return
    drag.current = { x: event.clientX, y: event.clientY, originX: position.x, originY: position.y }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return
    setPosition({ x: drag.current.originX + event.clientX - drag.current.x, y: drag.current.originY + event.clientY - drag.current.y })
  }
  function endDrag() { drag.current = null }
  function enterSite() { document.getElementById('kapex-details')?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' }) }

  return (
    <main className="kapex-landing">
      <header className="map-nav">
        <button className="brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} aria-label="KapexAI home"><i>K</i><span>kapex<span>ai</span></span></button>
        <div className="nav-actions">
          <button className={`roam-toggle ${freeRoam ? 'is-active' : ''}`} onClick={() => setFreeRoam((value) => !value)}>{freeRoam ? 'Exit map' : 'Free roam'} <Compass size={15} /></button>
          <button className="workspace-link" onClick={() => user ? navigate('/chat') : document.getElementById('central-access')?.scrollIntoView({ behavior: 'smooth' })}>{user ? 'Workspace' : 'Sign in'} <ArrowUpRight size={15} /></button>
        </div>
      </header>

      <section className={`map-stage ${freeRoam ? 'is-roaming' : ''}`} onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} aria-label="KapexAI capability map">
        <div className="map-grain" />
        <div className="orb orb-one" /><div className="orb orb-two" />
        <div className="map-label label-one">NORTH / STRATEGY</div><div className="map-label label-two">SIGNAL NETWORK</div>
        <motion.div className="world" animate={position} transition={{ type: 'spring', stiffness: 155, damping: 27, mass: .7 }}>
          <svg className="routes" viewBox="0 0 1200 760" aria-hidden="true"><path d="M70 165 C260 115 355 285 550 335 S880 190 1130 125" /><path d="M125 630 C330 510 400 565 595 425 S895 580 1085 485" /><circle cx="550" cy="335" r="4" /><circle cx="595" cy="425" r="4" /></svg>
          {TOOLS_DATA.map((tool, index) => {
            const Icon = iconFor(tool.iconName)
            return <motion.button key={tool.id} className="tool-island" style={{ '--x': `${tool.x}px`, '--y': `${tool.y}px` } as CSSProperties} onClick={() => setSelectedTool(tool)} initial={{ opacity: 0, filter: 'blur(8px)' }} animate={{ opacity: 1, filter: 'blur(0px)' }} transition={{ delay: .25 + index * .08, duration: .65 }} whileHover={{ y: -5 }}>
              <span className="tool-icon"><Icon size={18} /></span><span className="tool-copy"><small>{tool.category}</small><strong>{tool.title}</strong><em>{tool.description}</em></span><span className="tool-arrow"><ArrowUpRight size={15} /></span>
            </motion.button>
          })}
          <motion.div id="central-access" className="central-station" initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .8 }}>
            <div className="station-ring"><Sparkles size={16} /></div><p>AI CONSULTING, RECOMPOSED</p><h1>Clarity for<br /><i>decisive</i> leaders.</h1><span>Independent intelligence for strategy, finance, and market opportunity.</span>
            {loading ? <div className="access-loading" /> : user ? <button className="primary-cta" onClick={() => navigate('/chat')}>Enter workspace <ArrowUpRight size={16} /></button> : <div className="google-wrap"><GoogleSignInButton width={264} /><small>Secure access · no credit card required</small></div>}
          </motion.div>
        </motion.div>
        <button className="details-trigger" onClick={enterSite}><span>Discover the practice</span><ArrowDown size={17} /></button>
        {freeRoam && <p className="roam-instruction">Drag anywhere to navigate the intelligence map</p>}
      </section>

      <AnimatePresence>{selectedTool && <motion.div className="tool-dialog-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={() => setSelectedTool(null)}><motion.article className="tool-dialog" initial={{ opacity: 0, y: 12, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12 }} onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${selectedTool.title} details`}><button className="close-dialog" onClick={() => setSelectedTool(null)} aria-label="Close"><X size={18} /></button><small>{selectedTool.category} capability</small><h2>{selectedTool.title}</h2><p>{selectedTool.description}</p><div className="dialog-rule" /><p className="dialog-note">Built to turn an open question into a defensible executive decision, with a clear line of reasoning.</p><button className="primary-cta" onClick={() => navigate(user ? '/chat' : '/')}>Explore in workspace <ArrowUpRight size={16} /></button></motion.article></motion.div>}</AnimatePresence>

      <div id="kapex-details" className="practice-site">
        <section className="practice-intro"><p className="eyebrow">THE KAPEXAI ADVANTAGE</p><h2>Move from ambiguity to a boardroom-ready point of view.</h2><p>KapexAI combines rigorous consulting frameworks with an always-on analytical partner. No decks full of filler. Just the signal needed to make the next decision.</p></section>
        <section className="principles"><article><b>01</b><h3>Evidence first</h3><p>Market intelligence grounded in current signals, not generic answers.</p></article><article><b>02</b><h3>One connected view</h3><p>Strategy, capital, competition, and execution considered together.</p></article><article><b>03</b><h3>Built for momentum</h3><p>Refine an answer as your context changes, without starting over.</p></article></section>
        <section className="closing-cta"><p className="eyebrow">YOUR NEXT DECISION</p><h2>Start with the question that matters most.</h2><button className="primary-cta" onClick={() => user ? navigate('/chat') : window.scrollTo({ top: 0, behavior: 'smooth' })}>{user ? 'Open workspace' : 'Access KapexAI'} <ArrowUpRight size={16} /></button></section>
        <footer><span>© {new Date().getFullYear()} KapexAI</span><span>Intelligence, made useful.</span></footer>
      </div>
    </main>
  )
}
