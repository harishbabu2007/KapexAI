import { motion, useScroll, useTransform } from 'framer-motion'
import { Menu, X, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { MagneticButton } from '../hooks/useScrollAnimations'

export function Navbar() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const { scrollY } = useScroll()
  
  const navBg = useTransform(scrollY, [0, 100], ['rgba(10, 10, 15, 0)', 'rgba(10, 10, 15, 0.9)'])
  const navBlur = useTransform(scrollY, [0, 100], ['0px', '20px'])
  const borderOpacity = useTransform(scrollY, [0, 100], [0, 1])
  
  return (
    <motion.nav
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: navBg,
        backdropFilter: navBlur,
        borderBottom: `1px solid rgba(39, 39, 46, ${borderOpacity})`,
        transition: 'all 0.3s ease',
      }}
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className="container" style={{ height: '72px' }}>
        <div className="flex items-center justify-between h-full">
          <motion.a
            href="#"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-3"
            style={{ textDecoration: 'none' }}
          >
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-pink-500 flex items-center justify-center glow">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-white to-indigo-300 bg-clip-text text-transparent">
              KapexAI
            </span>
          </motion.a>
          
          <div className="hidden md:flex items-center gap-8">
            {['Features', 'How It Works', 'Pricing', 'Docs'].map((item) => (
              <motion.a
                key={item}
                href={`#${item.toLowerCase().replace(' ', '-')}`}
                whileHover={{ y: -2 }}
                className="text-sm font-medium text-zinc-400 hover:text-white transition-colors relative"
              >
                {item}
                <motion.span
                  layoutId="underline"
                  className="absolute bottom -4 left-0 right-0 h-0.5 bg-gradient-to-r from-indigo-500 to-pink-500 rounded-full origin-center"
                  initial={{ scaleX: 0 }}
                  style={{ display: 'none' }}
                />
              </motion.a>
            ))}
          </div>
          
          <div className="hidden md:flex items-center gap-4">
            <MagneticButton className="px-6 py-2.5 rounded-xl border border-zinc-700 text-zinc-300 font-medium hover:border-indigo-500/50 hover:text-white transition-all">
              Sign In
            </MagneticButton>
            <MagneticButton
              onClick={() => window.location.href = '/auth/google'}
              className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium glow-subtle"
            >
              Get Started
            </MagneticButton>
          </div>
          
          <button
            className="md:hidden p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Toggle menu"
          >
            {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>
      
      {isMenuOpen && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="md:hidden border-t border-zinc-800 bg-zinc-950/95 backdrop-blur-xl"
        >
          <div className="container py-6 space-y-4">
            {['Features', 'How It Works', 'Pricing', 'Docs'].map((item) => (
              <a
                key={item}
                href={`#${item.toLowerCase().replace(' ', '-')}`}
                className="block px-4 py-3 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors font-medium"
                onClick={() => setIsMenuOpen(false)}
              >
                {item}
              </a>
            ))}
            <div className="pt-4 space-y-3 border-t border-zinc-800">
              <MagneticButton className="w-full px-6 py-3 rounded-xl border border-zinc-700 text-zinc-300 font-medium hover:border-indigo-500/50 hover:text-white transition-all">
                Sign In
              </MagneticButton>
              <MagneticButton
                onClick={() => window.location.href = '/auth/google'}
                className="w-full px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium glow-subtle"
              >
                Get Started
              </MagneticButton>
            </div>
          </div>
        </motion.div>
      )}
    </motion.nav>
  )
}