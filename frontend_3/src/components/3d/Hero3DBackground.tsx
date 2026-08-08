import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { Suspense, useRef, useEffect, useState, createContext, useContext } from 'react'
import * as THREE from 'three'
import { extend } from '@react-three/fiber'
import { motion } from 'framer-motion'
import { shaderMaterial } from '@react-three/drei'

extend({ shaderMaterial })

const vertexShader = `
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vPosition;
  
  void main() {
    vUv = uv;
    vNormal = normalize(normalMatrix * normal);
    vPosition = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const fragmentShader = `
  uniform float uTime;
  uniform vec3 uColor1;
  uniform vec3 uColor2;
  uniform vec3 uColor3;
  uniform vec2 uMouse;
  
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vPosition;
  
  float noise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(
        mix(dot(i + vec3(0,0,0), f), dot(i + vec3(1,0,0), f), f.x),
        mix(dot(i + vec3(0,1,0), f), dot(i + vec3(1,1,0), f), f.x),
        f.y
      ),
      mix(
        mix(dot(i + vec3(0,0,1), f), dot(i + vec3(1,0,1), f), f.x),
        mix(dot(i + vec3(0,1,1), f), dot(i + vec3(1,1,1), f), f.x),
        f.y
      ),
      f.z
    );
  }
  
  float fbm(vec3 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 5; i++) {
      value += amplitude * noise(p);
      p *= 2.0;
      amplitude *= 0.5;
    }
    return value;
  }
  
  void main() {
    vec3 pos = vPosition * 0.5;
    float n = fbm(pos + uTime * 0.1);
    float n2 = fbm(pos * 2.0 - uTime * 0.05);
    
    vec3 color = mix(uColor1, uColor2, n);
    color = mix(color, uColor3, n2 * 0.5);
    
    float fresnel = pow(1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), 2.0);
    color += vec3(fresnel) * uColor3 * 0.3;
    
    vec2 mouseInfluence = uMouse * 0.3;
    float mouseDist = length(vUv - 0.5 - mouseInfluence * 0.5);
    color += vec3(1.0 - mouseDist) * uColor3 * 0.15;
    
    float alpha = 0.15 + n * 0.1 + fresnel * 0.3;
    
    gl_FragColor = vec4(color, alpha);
  }
`

const OrbMaterial = shaderMaterial(
  {
    uTime: 0,
    uMouse: new THREE.Vector2(0, 0),
    uColor1: new THREE.Color(0x6366f1),
    uColor2: new THREE.Color(0x8b5cf6),
    uColor3: new THREE.Color(0xec4899),
  },
  vertexShader,
  fragmentShader
)

interface MouseContextValue {
  x: number
  y: number
}

const MouseContext = createContext<MouseContextValue>({ x: 0, y: 0 })

function FloatingOrbs() {
  const meshRef = useRef<THREE.Mesh>(null)
  const timeRef = useRef(0)
  const targetRotation = useRef({ x: 0, y: 0 })
  const currentRotation = useRef({ x: 0, y: 0 })
  const { x: mouseX, y: mouseY } = useContext(MouseContext)
  
  useEffect(() => {
    const animate = () => {
      timeRef.current += 0.01
      if (meshRef.current) {
        const material = meshRef.current.material as THREE.ShaderMaterial
        material.uniforms.uTime.value = timeRef.current
        material.uniforms.uMouse.value.set(mouseX, mouseY)
        
        targetRotation.current.y = mouseX * 0.3
        targetRotation.current.x = -mouseY * 0.3
        
        currentRotation.current.x += (targetRotation.current.x - currentRotation.current.x) * 0.05
        currentRotation.current.y += (targetRotation.current.y - currentRotation.current.y) * 0.05
        
        meshRef.current.rotation.x = currentRotation.current.x
        meshRef.current.rotation.y = currentRotation.current.y
      }
      requestAnimationFrame(animate)
    }
    animate()
  }, [mouseX, mouseY])
  
  return (
    <mesh ref={meshRef} scale={2.5}>
      <sphereGeometry args={[1, 64, 64]} />
      <primitive object={new OrbMaterial({
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })} />
    </mesh>
  )
}

function ParticleField() {
  const pointsRef = useRef<THREE.Points>(null)
  const timeRef = useRef(0)
  
  useEffect(() => {
    if (!pointsRef.current) return
    
    const geometry = pointsRef.current.geometry
    const positions = geometry.attributes.position.array
    const velocities = new Float32Array(positions.length)
    
    for (let i = 0; i < positions.length; i += 3) {
      velocities[i] = (Math.random() - 0.5) * 0.0005
      velocities[i + 1] = (Math.random() - 0.5) * 0.0005
      velocities[i + 2] = (Math.random() - 0.5) * 0.0005
    }
    
    geometry.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3))
    
    const animate = () => {
      timeRef.current += 0.016
      const pos = geometry.attributes.position.array
      const vel = geometry.attributes.velocity.array
      
      for (let i = 0; i < pos.length; i += 3) {
        pos[i] += vel[i]
        pos[i + 1] += vel[i + 1]
        pos[i + 2] += vel[i + 2]
        
        if (Math.abs(pos[i]) > 50) vel[i] *= -1
        if (Math.abs(pos[i + 1]) > 50) vel[i + 1] *= -1
        if (Math.abs(pos[i + 2]) > 50) vel[i + 2] *= -1
      }
      
      geometry.attributes.position.needsUpdate = true
      pointsRef.current!.rotation.y += 0.00005
      requestAnimationFrame(animate)
    }
    animate()
  }, [])
  
  return (
    <points ref={pointsRef}>
      <bufferGeometry attach="geometry">
        <bufferAttribute
          attach="attributes-position"
          count={3000}
          array={new Float32Array(3000 * 3).map(() => (Math.random() - 0.5) * 100)}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-size"
          count={3000}
          array={new Float32Array(3000).map(() => Math.random() * 2 + 0.5)}
          itemSize={1}
        />
      </bufferGeometry>
      <pointsMaterial
        size={1}
        sizeAttenuation
        transparent
        opacity={0.6}
        color="#6366f1"
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  )
}

function GridFloor() {
  const gridRef = useRef<THREE.GridHelper>(null)
  const timeRef = useRef(0)
  const { x: mouseX, y: mouseY } = useContext(MouseContext)
  
  useEffect(() => {
    const animate = () => {
      timeRef.current += 0.01
      if (gridRef.current) {
        const material = gridRef.current.material as THREE.Material
        material.opacity = 0.03 + Math.sin(timeRef.current) * 0.02 + Math.abs(mouseX) * 0.02
      }
      if (gridRef.current) {
        gridRef.current.rotation.z = mouseX * 0.02
      }
      requestAnimationFrame(animate)
    }
    animate()
  }, [mouseX, mouseY])
  
  return (
    <gridHelper
      ref={gridRef}
      args={[100, 100, 0x27272e, 0x6366f1]}
      position={[0, -5, 0]}
    />
  )
}

function Hero3DCanvas() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  
  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    const y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    setMousePos({ x, y })
  }
  
  return (
    <MouseContext.Provider value={mousePos}>
      <Canvas
        camera={{ position: [0, 0, 30], fov: 50 }}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 0 }}
        gl={{ antialias: true, alpha: true, preserveDrawingBuffer: false }}
        onPointerMove={handleMouseMove}
        onClick={handleMouseMove}
      >
        <color attach="background" args={['#0a0a0f']} />
        <fog attach="fog" args={['#0a0a0f', 10, 80]} />
        
        <ambientLight intensity={0.3} />
        <directionalLight position={[10, 10, 10]} intensity={0.5} color="#6366f1" />
        <directionalLight position={[-10, -5, 5]} intensity={0.3} color="#ec4899" />
        <pointLight position={[0, 5, 10]} intensity={0.5} color="#8b5cf6" distance={50} decay={2} />
        
        <Suspense fallback={null}>
          <FloatingOrbs />
          <ParticleField />
          <GridFloor />
        </Suspense>
        
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          enableRotate={true}
          autoRotate={true}
          autoRotateSpeed={0.1}
          minPolarAngle={Math.PI / 3}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>
    </MouseContext.Provider>
  )
}

function HeroContent() {
  const styleRef = useRef<HTMLStyleElement>(null)
  
  useEffect(() => {
    if (styleRef.current) {
      styleRef.current.textContent = `
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 60px rgba(99, 102, 241, 0.4), 0 0 120px rgba(236, 72, 153, 0.2); }
          50% { box-shadow: 0 0 80px rgba(99, 102, 241, 0.6), 0 0 160px rgba(236, 72, 153, 0.3); }
        }
      `
    }
  }, [])
  
  return (
    <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 text-center w-full">
      <style ref={styleRef} />
      
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.8, ease: [0.34, 1.56, 0.64, 1] }}
        className="glow mb-8"
        style={{
          width: '100px',
          height: '100px',
          borderRadius: '28px',
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 60px rgba(99, 102, 241, 0.4), 0 0 120px rgba(236, 72, 153, 0.2)',
          animation: 'pulse 3s ease-in-out infinite',
        }}
      >
        <span style={{ fontSize: '48px', fontWeight: 700, fontFamily: 'Space Grotesk', color: 'white' }}>K</span>
      </motion.div>
      
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.8 }}
        className="max-w-4xl mx-auto mb-6"
        style={{
          fontSize: 'clamp(40px, 8vw, 80px)',
          fontWeight: 700,
          letterSpacing: '-0.03em',
          background: 'linear-gradient(135deg, #fff 0%, #a5b4fc 50%, #f9a8d4 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}
      >
        KapexAI
      </motion.h1>
      
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.8 }}
        className="max-w-2xl mx-auto mb-10"
        style={{
          fontSize: 'clamp(18px, 2.5vw, 24px)',
          color: '#a1a1aa',
          fontWeight: 400,
          lineHeight: 1.6,
        }}
      >
        Your AI Business Consultant. Transform ideas into strategic plans with intelligent analysis, research, and actionable insights.
      </motion.p>
      
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.8 }}
        className="flex flex-col sm:flex-row gap-4 justify-center items-center w-full max-w-md"
      >
        <GoogleSignInButton />
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="w-full sm:w-auto px-8 py-4 rounded-xl border border-zinc-700 text-zinc-300 font-semibold text-lg hover:border-indigo-500/50 hover:text-white hover:bg-zinc-800/50 transition-all backdrop-blur-xl"
        >
          Explore Demo
        </motion.button>
      </motion.div>
    </div>
  )
}

function GoogleSignInButton() {
  return (
    <motion.button
      whileHover={{ scale: 1.02, boxShadow: '0 0 30px rgba(99, 102, 241, 0.3)' }}
      whileTap={{ scale: 0.98 }}
      onClick={() => window.location.href = '/auth/google'}
      className="w-full sm:w-auto px-8 py-4 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-semibold text-lg glow-subtle flex items-center justify-center gap-3"
    >
      <svg width="20" height="20" viewBox="0 0 24 24">
        <path
          fill="currentColor"
          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        />
        <path
          fill="currentColor"
          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        />
        <path
          fill="currentColor"
          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        />
        <path
          fill="currentColor"
          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        />
      </svg>
      <span>Continue with Google</span>
    </motion.button>
  )
}

export function Hero3DBackground() {
  return (
    <section className="relative w-full min-h-screen overflow-hidden" style={{ height: '100vh' }}>
      <Hero3DCanvas />
      <HeroContent />
    </section>
  )
}