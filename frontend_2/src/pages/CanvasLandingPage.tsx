import { motion, type MotionProps, useReducedMotion } from 'framer-motion'
import { ArrowDown, ArrowRight, BarChart3, CircleDollarSign, Compass, LineChart, Menu, Search, ShieldCheck, Sparkles, X } from 'lucide-react'
import { type CSSProperties, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GoogleSignInButton } from '../components/auth/GoogleSignInButton'
import { TOOLS_DATA } from '../constants/tools'
import { useAuth } from '../lib/auth'
import '../styles/broadcast-landing.css'

const toolIcons = [Compass, CircleDollarSign, Search, LineChart, ShieldCheck, BarChart3]

export function CanvasLandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()
  const reducedMotion = useReducedMotion()
  const [menuOpen, setMenuOpen] = useState(false)
  const [activeTool, setActiveTool] = useState(0)
  const scrollToDetails = () => document.querySelector('#details')?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth' })
  const reveal: MotionProps = {
    initial: { opacity: 0, y: reducedMotion ? 0 : 24 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: false, margin: '0px 0px -80px 0px' },
    transition: { duration: 0.6, ease: 'easeOut' },
  }

  return (
    <main className="broadcast-page">
      <section className="broadcast-hero">
        <nav className="broadcast-nav" aria-label="Main navigation">
          <button className="wordmark" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} aria-label="KapexAI home"><span>k</span>kapex<span>ai</span></button>
          <div className={menuOpen ? 'links open' : 'links'}><a href="#details">Practice</a><a href="#capabilities">Capabilities</a><a href="#approach">Approach</a></div>
          <div className="nav-login"><button onClick={() => user ? navigate('/chat') : document.querySelector('#access')?.scrollIntoView({ behavior: 'smooth' })}>{user ? 'Workspace' : 'Sign in'} <ArrowRight size={14} /></button><button className="menu" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation">{menuOpen ? <X size={18} /> : <Menu size={18} />}</button></div>
        </nav>
        <div className="hero-copy" id="access">
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .1 }}>AI BUSINESS INTELLIGENCE / EST. 2026</motion.p>
          <motion.h1 initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .75 }}>Make the<br /><i>next move</i><br />obvious.</motion.h1>
          <motion.div className="access-panel" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .4, duration: .6 }}>{loading ? <span className="loading-dot" /> : user ? <button className="bright-button" onClick={() => navigate('/chat')}>Enter your workspace <ArrowRight size={16} /></button> : <GoogleSignInButton width={248} />}<small>Private, secure access for better decisions.</small></motion.div>
        </div>
        <div className="signal-station" aria-label="KapexAI tools broadcast">
          <div className="station-core"><div className="core-rings" /><Sparkles size={24} /><span>LIVE<br />SIGNAL</span></div><div className="signal-beam" />
          {TOOLS_DATA.map((tool, index) => { const Icon = toolIcons[index] ?? Sparkles; return <motion.button key={tool.id} className={`broadcast-tool ${activeTool === index ? 'active' : ''}`} style={{ '--offset': index } as CSSProperties} onMouseEnter={() => setActiveTool(index)} onFocus={() => setActiveTool(index)} onClick={() => setActiveTool(index)} initial={{ opacity: 0, x: -25 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: .45 + index * .1 }}><span><Icon size={17} /></span><b>{tool.title}</b><em>{tool.category}</em></motion.button> })}
          <motion.div className="tool-readout" key={TOOLS_DATA[activeTool].id} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }}><span>NOW TRANSMITTING</span><strong>{TOOLS_DATA[activeTool].description}</strong></motion.div>
        </div>
        <button className="scroll-cue" onClick={scrollToDetails}>Scroll to explore <ArrowDown size={17} /></button><div className="hero-footer"><span>STRATEGY / FINANCE / MARKET INTELLIGENCE</span><span>01 — 05</span></div>
      </section>
      <motion.section className="manifesto" id="details" {...reveal}><p className="section-label">THE KAPEXAI PRACTICE</p><h2>The counsel you need.<br /><i>At the pace you operate.</i></h2><p className="manifesto-copy">KapexAI turns your most consequential business questions into clear, evidence-led paths forward. Strategy, finance, and market intelligence—connected in one working session.</p></motion.section>
      <motion.section className="capabilities" id="capabilities" {...reveal}><div className="cap-heading"><p className="section-label">WHAT WE BROADCAST</p><h2>A complete view<br />of the decision.</h2></div><div className="cap-list">{TOOLS_DATA.map((tool, index) => { const Icon = toolIcons[index] ?? Sparkles; return <article key={tool.id}><span>0{index + 1}</span><Icon size={20} /><h3>{tool.title}</h3><p>{tool.description}</p><ArrowRight size={18} /></article> })}</div></motion.section>
      <motion.section className="approach" id="approach" {...reveal}><p className="section-label">HOW IT WORKS</p><div className="approach-grid"><h2>One question.<br /><i>A sharper</i><br />position.</h2><ol><li><span>01</span><div><h3>Frame the question</h3><p>Bring the decision, the data, or simply the uncertainty.</p></div></li><li><span>02</span><div><h3>Interrogate the signals</h3><p>Specialized AI agents connect market evidence, financial logic, and competitive context.</p></div></li><li><span>03</span><div><h3>Commit with clarity</h3><p>Leave with a defensible recommendation and the reasoning behind it.</p></div></li></ol></div></motion.section>
      <motion.section className="proof" {...reveal}><p className="section-label">EXECUTIVE-GRADE, ON DEMAND</p><div><h2>Less reporting.<br />More <i>conviction.</i></h2><button className="bright-button" onClick={() => user ? navigate('/chat') : window.scrollTo({ top: 0, behavior: 'smooth' })}>Start a strategic session <ArrowRight size={16} /></button></div><div className="proof-stats"><span><b>3×</b>faster strategic iteration</span><span><b>24/7</b>intelligence availability</span><span><b>01</b>connected workspace</span></div></motion.section>
      <motion.section className="faq" {...reveal}><p className="section-label">COMMON QUESTIONS</p><h2>Built for important work.</h2>{['What does KapexAI help me decide?', 'How is this different from a general AI chatbot?', 'Is my business context kept private?'].map((question, index) => <details key={question} open={index === 0}><summary>{question}<span>+</span></summary><p>{index === 0 ? 'From market entry to financial viability and competitive positioning, KapexAI helps you inspect the decision from every useful angle.' : 'KapexAI is designed around structured consulting workflows, giving business context and analytical rigor a first-class role.'}</p></details>)}</motion.section>
      <motion.footer {...reveal}><button className="wordmark" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}><span>k</span>kapex<span>ai</span></button><p>Independent intelligence for decisive teams.</p><span>© {new Date().getFullYear()} KapexAI</span></motion.footer>
    </main>
  )
}
