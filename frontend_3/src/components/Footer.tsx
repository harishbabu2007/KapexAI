import { motion } from 'framer-motion'
import { Sparkles, Link2, Mail, ArrowUp, ExternalLink } from 'lucide-react'
import { MagneticButton } from '../hooks/useScrollAnimations'

export function Footer() {
  return (
    <footer className="relative border-t border-zinc-800 bg-zinc-950/50 backdrop-blur-xl">
      <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 to-transparent" />
      
      <div className="container relative py-16 md:py-24">
        <div className="grid md:grid-cols-4 gap-12 mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
            className="md:col-span-2"
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-pink-500 flex items-center justify-center glow">
                <Sparkles className="w-7 h-7 text-white" />
              </div>
              <span className="text-2xl font-bold bg-gradient-to-r from-white to-indigo-300 bg-clip-text text-transparent">
                KapexAI
              </span>
            </div>
            <p className="text-zinc-400 max-w-md leading-relaxed mb-8">
              Your AI Business Consultant. Transform ideas into strategic plans with intelligent analysis, research, and actionable insights.
            </p>
            <div className="flex gap-4">
              {[
                { icon: Link2, href: '#', label: 'Twitter' },
                { icon: ExternalLink, href: '#', label: 'GitHub' },
                { icon: Link2, href: '#', label: 'LinkedIn' },
                { icon: Mail, href: '#', label: 'Email' },
              ].map((social) => (
                <motion.a
                  key={social.label}
                  href={social.href}
                  whileHover={{ scale: 1.1, y: -2 }}
                  whileTap={{ scale: 0.9 }}
                  className="w-11 h-11 rounded-xl bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-400 hover:text-white hover:border-indigo-500/50 hover:bg-zinc-700/50 transition-all"
                  aria-label={social.label}
                >
                  <social.icon className="w-5 h-5" />
                </motion.a>
              ))}
            </div>
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
          >
            <h4 className="font-semibold mb-4">Product</h4>
            <nav className="space-y-3">
              {['Features', 'Pricing', 'Documentation', 'API Reference', 'Changelog', 'Roadmap'].map((item) => (
                <a key={item} href="#" className="block text-zinc-400 hover:text-white transition-colors text-sm">
                  {item}
                </a>
              ))}
            </nav>
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
          >
            <h4 className="font-semibold mb-4">Company</h4>
            <nav className="space-y-3">
              {['About', 'Blog', 'Careers', 'Press', 'Contact', 'Partners'].map((item) => (
                <a key={item} href="#" className="block text-zinc-400 hover:text-white transition-colors text-sm">
                  {item}
                </a>
              ))}
            </nav>
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.4 }}
          >
            <h4 className="font-semibold mb-4">Legal</h4>
            <nav className="space-y-3">
              {['Privacy Policy', 'Terms of Service', 'Cookie Policy', 'Security', 'GDPR'].map((item) => (
                <a key={item} href="#" className="block text-zinc-400 hover:text-white transition-colors text-sm">
                  {item}
                </a>
              ))}
            </nav>
          </motion.div>
        </div>
        
        <div className="pt-8 border-t border-zinc-800 flex flex-col md:flex-row justify-between items-center gap-6">
          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="text-zinc-500 text-sm"
          >
            © {new Date().getFullYear()} KapexAI. All rights reserved.
          </motion.p>
          
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="flex items-center gap-4"
          >
            <MagneticButton className="p-2 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-white hover:border-indigo-500/50 transition-all">
              <ArrowUp className="w-5 h-5" />
            </MagneticButton>
          </motion.div>
        </div>
      </div>
    </footer>
  )
}