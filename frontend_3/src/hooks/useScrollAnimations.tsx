import { useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

interface SectionProps {
  children: React.ReactNode
  id?: string
  className?: string
}

export function AnimatedSection({ children, id, className = '' }: SectionProps) {
  const sectionRef = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    const ctx = gsap.context(() => {
      const elements = sectionRef.current?.querySelectorAll('[data-animate]')
      elements?.forEach((el, i) => {
        gsap.fromTo(el, 
          { opacity: 0, y: 60 },
          {
            opacity: 1,
            y: 0,
            duration: 1,
            ease: 'power3.out',
            delay: i * 0.1,
            scrollTrigger: {
              trigger: el,
              start: 'top 85%',
              end: 'bottom 20%',
              toggleActions: 'play none none reverse',
            }
          }
        )
      })
      
      const staggerElements = sectionRef.current?.querySelectorAll('[data-stagger]')
      staggerElements?.forEach((container) => {
        const items = container.querySelectorAll('[data-stagger-item]')
        gsap.fromTo(items,
          { opacity: 0, y: 40 },
          {
            opacity: 1,
            y: 0,
            duration: 0.8,
            ease: 'power3.out',
            stagger: 0.1,
            scrollTrigger: {
              trigger: container,
              start: 'top 80%',
              toggleActions: 'play none none reverse',
            }
          }
        )
      })
    }, sectionRef)
    
    return () => ctx.revert()
  }, [])
  
  return (
    <motion.section
      ref={sectionRef}
      id={id}
      className={className}
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: '-100px' }}
      style={{ position: 'relative', zIndex: 10 }}
    >
      {children}
    </motion.section>
  )
}

export function ScrollProgress() {
  const progressRef = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.to(progressRef.current, {
        scaleX: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: document.body,
          start: 'top top',
          end: 'bottom bottom',
          scrub: 0.1,
        }
      })
    })
    return () => ctx.revert()
  }, [])
  
  return (
    <motion.div
      ref={progressRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '3px',
        background: 'linear-gradient(90deg, #6366f1, #ec4899)',
        transformOrigin: 'left center',
        scaleX: 0,
        zIndex: 9999,
      }}
    />
  )
}

export function ParallaxElement({ children, speed = 0.5, className = '' }: { 
  children: React.ReactNode
  speed?: number
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.to(ref.current, {
        yPercent: -100 * speed,
        ease: 'none',
        scrollTrigger: {
          trigger: ref.current,
          start: 'top bottom',
          end: 'bottom top',
          scrub: true,
        }
      })
    }, ref)
    return () => ctx.revert()
  }, [speed])
  
  return (
    <motion.div ref={ref} className={className} style={{ willChange: 'transform' }}>
      {children}
    </motion.div>
  )
}

interface MagneticButtonProps {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  onClick?: React.MouseEventHandler<HTMLButtonElement>
}

export function MagneticButton({ children, className, style, onClick, ...props }: MagneticButtonProps) {
  const ref = useRef<HTMLButtonElement>(null)
  
  useEffect(() => {
    const el = ref.current
    if (!el) return
    
    const handleMouseMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect()
      const x = e.clientX - rect.left - rect.width / 2
      const y = e.clientY - rect.top - rect.height / 2
      
      gsap.to(el, {
        x: x * 0.3,
        y: y * 0.3,
        duration: 0.3,
        ease: 'power2.out'
      })
    }
    
    const handleMouseLeave = () => {
      gsap.to(el, {
        x: 0,
        y: 0,
        duration: 0.5,
        ease: 'elastic.out(1, 0.5)'
      })
    }
    
    el.addEventListener('mousemove', handleMouseMove)
    el.addEventListener('mouseleave', handleMouseLeave)
    
    return () => {
      el.removeEventListener('mousemove', handleMouseMove)
      el.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [])
  
  return (
    <motion.button
      ref={ref}
      className={className}
      style={style}
      onClick={onClick}
      whileTap={{ scale: 0.95 }}
      {...props}
    >
      {children}
    </motion.button>
  )
}