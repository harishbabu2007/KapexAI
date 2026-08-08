import { Navbar } from './components/Navbar'
import { Footer } from './components/Footer'
import { Hero3DBackground } from './components/3d/Hero3DBackground'
import { FeaturesSection, StatsSection, HowItWorksSection, CTASection } from './components/Sections'
import { ScrollProgress } from './hooks/useScrollAnimations'

function App() {
  return (
    <>
      <ScrollProgress />
      <Navbar />
      
      <main>
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
          <Hero3DBackground />
        </section>
        
        <FeaturesSection />
        <StatsSection />
        <HowItWorksSection />
        <CTASection />
      </main>
      
      <Footer />
    </>
  )
}

export default App