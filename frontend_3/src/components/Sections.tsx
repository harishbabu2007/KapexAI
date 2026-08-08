import { motion } from 'framer-motion'
import { 
  Zap, Brain, Search, BarChart3, Shield, Lightbulb, 
  ArrowRight, CheckCircle, Target, Sparkles
} from 'lucide-react'
import { AnimatedSection, MagneticButton } from '../hooks/useScrollAnimations'

const features = [
  {
    icon: Brain,
    title: 'AI Business Consultant',
    description: 'Get expert-level business guidance powered by advanced AI. From ideation to execution strategy.',
    gradient: 'from-indigo-500 to-purple-600',
  },
  {
    icon: Search,
    title: 'Deep Market Research',
    description: 'Automated web research on competitors, markets, and trends. Real-time data intelligence.',
    gradient: 'from-purple-500 to-pink-600',
  },
  {
    icon: BarChart3,
    title: 'SWOT Analysis',
    description: 'Comprehensive Strengths, Weaknesses, Opportunities, Threats analysis tailored to your business.',
    gradient: 'from-pink-500 to-rose-500',
  },
  {
    icon: Zap,
    title: 'Instant Insights',
    description: 'Real-time streaming responses. See your analysis build live with interactive visualizations.',
    gradient: 'from-indigo-500 to-blue-500',
  },
  {
    icon: Shield,
    title: 'Secure & Private',
    description: 'Enterprise-grade security with Google OAuth. Your business data stays confidential.',
    gradient: 'from-green-500 to-teal-500',
  },
  {
    icon: Lightbulb,
    title: 'Actionable Roadmaps',
    description: 'Step-by-step execution plans with milestones, resources, and risk mitigation strategies.',
    gradient: 'from-amber-500 to-orange-500',
  },
]

const stats = [
  { value: '10K+', label: 'Business Ideas Analyzed' },
  { value: '94%', label: 'User Satisfaction Rate' },
  { value: '50+', label: 'Analysis Tools Available' },
  { value: '24/7', label: 'AI Consultant Availability' },
]

export function FeaturesSection() {
  return (
    <AnimatedSection id="features" className="py-24 md:py-32" data-animate>
      <div className="container">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center max-w-3xl mx-auto mb-20"
        >
          <span className="inline-block px-4 py-2 rounded-full text-sm font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-6">
            Core Capabilities
          </span>
          <h2 className="text-4xl md:text-5xl font-bold mb-6 bg-gradient-to-r from-white via-indigo-300 to-pink-300 bg-clip-text text-transparent">
            Everything you need to validate & scale your business
          </h2>
          <p className="text-lg text-zinc-400 leading-relaxed">
            Powerful AI tools designed specifically for entrepreneurs and business strategists
          </p>
        </motion.div>
        
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-stagger>
          {features.map((feature) => (
            <motion.div
              key={feature.title}
              data-stagger-item
              className="group relative p-8 bg-zinc-900/50 backdrop-blur-xl rounded-2xl border border-zinc-800 hover:border-indigo-500/30 transition-all duration-500 hover:shadow-[0_0_40px_rgba(99,102,241,0.1)]"
              style={{ willChange: 'transform, box-shadow, border-color' }}
            >
              <div className={`w-14 h-14 rounded-xl bg-gradient-to-br ${feature.gradient} flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                <feature.icon className="w-7 h-7 text-white" strokeWidth={2} />
              </div>
              <h3 className="text-xl font-bold mb-3 group-hover:text-indigo-300 transition-colors">{feature.title}</h3>
              <p className="text-zinc-400 leading-relaxed mb-6">{feature.description}</p>
              <MagneticButton className="inline-flex items-center gap-2 text-sm font-medium text-indigo-400 hover:text-indigo-300 group">
                Learn more
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </MagneticButton>
            </motion.div>
          ))}
        </div>
      </div>
    </AnimatedSection>
  )
}

export function StatsSection() {
  return (
    <AnimatedSection id="stats" className="py-24 relative overflow-hidden" data-animate>
      <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/5 via-transparent to-pink-500/5" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-indigo-500/10 via-transparent to-pink-500/10" />
      
      <div className="container relative">
        <div className="grid md:grid-cols-4 gap-8 text-center" data-stagger>
          {stats.map((stat, index) => (
            <motion.div key={stat.label} data-stagger-item className="relative">
              <div className="relative mx-auto mb-4" style={{ width: '100px', height: '100px' }}>
                <svg viewBox="0 0 100 100" className="w-full h-full transform -rotate-90">
                  <circle
                    cx="50" cy="50" r="42"
                    fill="none"
                    stroke="#27272e"
                    strokeWidth="4"
                  />
                  <motion.circle
                    cx="50" cy="50" r="42"
                    fill="none"
                    stroke="url(#stat-gradient)"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeDasharray={264}
                    initial={{ strokeDashoffset: 264 }}
                    whileInView={{ strokeDashoffset: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 1.5, delay: index * 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
                  />
                  <defs>
                    <linearGradient id="stat-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#6366f1" />
                      <stop offset="100%" stopColor="#ec4899" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-white to-indigo-300 bg-clip-text text-transparent">
                    {stat.value}
                  </span>
                </div>
              </div>
              <p className="text-zinc-400 font-medium">{stat.label}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </AnimatedSection>
  )
}

export function HowItWorksSection() {
  const steps = [
    {
      number: '01',
      title: 'Describe Your Idea',
      description: 'Share your business concept in natural language. No templates or rigid forms needed.',
      icon: Lightbulb,
    },
    {
      number: '02',
      title: 'AI Asks Smart Questions',
      description: 'Our questionnaire agent gathers critical context through targeted, intelligent questions.',
      icon: Brain,
    },
    {
      number: '03',
      title: 'Deep Research & Analysis',
      description: 'Automated web research, SWOT analysis, and market intelligence compiled in real-time.',
      icon: Search,
    },
    {
      number: '04',
      title: 'Get Your Strategic Plan',
      description: 'Receive a comprehensive roadmap with actionable steps, resources, and success metrics.',
      icon: Target,
    },
  ]
  
  return (
    <AnimatedSection id="how-it-works" className="py-24 md:py-32" data-animate>
      <div className="container">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center max-w-3xl mx-auto mb-20"
        >
          <span className="inline-block px-4 py-2 rounded-full text-sm font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-6">
            How It Works
          </span>
          <h2 className="text-4xl md:text-5xl font-bold mb-6 bg-gradient-to-r from-white via-indigo-300 to-pink-300 bg-clip-text text-transparent">
            From idea to execution in 4 simple steps
          </h2>
          <p className="text-lg text-zinc-400 leading-relaxed">
            Our AI agent guides you through a structured process to validate and plan your business
          </p>
        </motion.div>
        
        <div className="relative">
          <div className="hidden lg:block absolute left-1/2 top-0 bottom-0 w-0.5 bg-gradient-to-b from-indigo-500/30 via-pink-500/30 to-transparent -translate-x-1/2" />
          
          <div className="space-y-16" data-stagger>
            {steps.map((step, index) => (
              <motion.div
                key={step.number}
                data-stagger-item
                className={`relative flex ${index % 2 === 0 ? 'flex-row' : 'flex-row-reverse'} gap-8 md:gap-16 items-start`}
              >
                <div className={`flex-1 ${index % 2 === 0 ? 'pr-8 text-right' : 'pl-8'}`}>
                  <div className="inline-flex items-center gap-3 mb-4">
                    <span className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-indigo-500 to-pink-500 bg-clip-text text-transparent">
                      {step.number}
                    </span>
                    <div className="w-16 h-0.5 bg-gradient-to-r from-indigo-500 to-pink-500" />
                  </div>
                  <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${index % 2 === 0 ? 'ml-auto' : 'mr-auto'} flex items-center justify-center mb-6`}>
                    <step.icon className="w-8 h-8 text-white" strokeWidth={2} />
                  </div>
                  <h3 className="text-2xl font-bold mb-3">{step.title}</h3>
                  <p className="text-zinc-400 leading-relaxed max-w-md mx-auto">{step.description}</p>
                </div>
                
                <div className="flex-1 relative">
                  <div className="aspect-video rounded-2xl bg-zinc-900/50 border border-zinc-800 overflow-hidden relative group">
                    <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-pink-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="text-center p-8">
                        <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-indigo-500/20 to-pink-500/20 flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
                          <Sparkles className="w-10 h-10 text-indigo-400" />
                        </div>
                        <p className="text-zinc-500">Step {step.number} Visualization</p>
                        <p className="text-xs text-zinc-600 mt-1">Interactive demo coming soon</p>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </AnimatedSection>
  )
}

export function CTASection() {
  return (
    <AnimatedSection id="cta" className="py-24 md:py-32 relative overflow-hidden" data-animate>
      <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 via-transparent to-pink-500/10" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-indigo-500/5 via-transparent to-pink-500/5" />
      
      <div className="container relative text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="max-w-3xl mx-auto"
        >
          <div className="inline-flex items-center gap-3 px-6 py-3 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-sm font-medium mb-8">
            <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
            <span>Ready to transform your business idea?</span>
          </div>
          
          <h2 className="text-4xl md:text-6xl font-bold mb-8 bg-gradient-to-r from-white via-indigo-300 to-pink-300 bg-clip-text text-transparent">
            Start Your Analysis Today
          </h2>
          
          <p className="text-lg md:text-xl text-zinc-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            Join thousands of entrepreneurs who use KapexAI to validate ideas, research markets, and build winning strategies.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <MagneticButton
              onClick={() => window.location.href = '/auth/google'}
              className="group relative px-8 py-4 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-semibold text-lg overflow-hidden"
            >
              <span className="relative z-10 flex items-center gap-3">
                <svg width="20" height="20" viewBox="0 0 24 24" className="group-hover:animate-bounce">
                  <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
                <span>Continue with Google</span>
              </span>
              <span className="absolute inset-0 bg-gradient-to-r from-purple-600 to-pink-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            </MagneticButton>
            
            <MagneticButton className="px-8 py-4 rounded-xl border border-zinc-700 text-zinc-300 font-semibold text-lg hover:border-indigo-500/50 hover:text-white transition-all duration-300">
              Watch Demo
            </MagneticButton>
          </div>
          
          <div className="mt-16 flex flex-wrap justify-center gap-8 text-zinc-500 text-sm">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-500" />
              <span>No credit card required</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-500" />
              <span>Free tier available</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-500" />
              <span>Cancel anytime</span>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatedSection>
  )
}