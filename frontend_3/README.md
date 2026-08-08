# KapexAI Frontend 3 - Premium 3D Landing Page

A premium, animated 3D landing page for KapexAI built with React, TypeScript, Vite, Three.js (React Three Fiber), Framer Motion, and GSAP.

## Features

- **3D Animated Background** - Floating orbs, particle field, and grid floor using React Three Fiber
- **Smooth Scroll Animations** - GSAP ScrollTrigger + Framer Motion for premium feel
- **Google OAuth Integration** - Ready for authentication
- **Magnetic Buttons** - Interactive hover effects
- **Responsive Design** - Works on all screen sizes
- **Premium Styling** - Dark theme with indigo/pink gradient accents

## Tech Stack

- React 18 + TypeScript
- Vite 7
- @react-three/fiber + @react-three/drei (3D)
- Framer Motion (animations)
- GSAP + ScrollTrigger (scroll animations)
- Lucide React (icons)
- @react-oauth/google (Google OAuth)

## Getting Started

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local
# Edit .env.local with your Google Client ID

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
src/
├── components/
│   ├── 3d/
│   │   └── Hero3DBackground.tsx    # 3D hero section with Three.js
│   ├── Navbar.tsx                  # Animated navigation bar
│   ├── Footer.tsx                  # Footer with links
│   └── Sections.tsx                # Feature, Stats, HowItWorks, CTA sections
├── hooks/
│   └── useScrollAnimations.tsx     # GSAP/Framer Motion scroll hooks
├── App.tsx                         # Main app component
├── main.tsx                        # Entry point
└── index.css                       # Global styles
```

## Customization

### Colors
Edit CSS variables in `src/index.css`:
```css
:root {
  --accent: #6366f1;        /* Primary indigo */
  --accent-secondary: #ec4899; /* Secondary pink */
  --bg: #0a0a0f;            /* Background */
  --fg: #fafafa;            /* Foreground text */
}
```

### 3D Scene
Modify `src/components/3d/Hero3DBackground.tsx` to customize:
- Orb colors and animation speed
- Particle count and behavior
- Camera position and orbit controls

### Animations
Adjust scroll animations in `src/hooks/useScrollAnimations.tsx`:
- Stagger delays
- Easing functions
- Trigger points

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID | Yes (for auth) |
| `VITE_API_BASE_URL` | Backend API URL | No (default: http://localhost:8000) |

## Performance Notes

- The 3D scene uses `requestAnimationFrame` for smooth 60fps animations
- GSAP ScrollTrigger is optimized with `gsap.context()` for proper cleanup
- Framer Motion handles layout animations efficiently
- Consider code-splitting for production (see build warning)

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

Requires WebGL 2.0 support for 3D graphics.