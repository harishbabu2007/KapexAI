import { useAuth } from '../../lib/auth'

export function LandingNav() {
  const { user } = useAuth()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-5 backdrop-blur-md bg-[#07111A]/80 border-b border-white/5">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center font-bold text-lg text-white shadow-lg shadow-blue-500/20">
          K
        </div>
        <span className="font-semibold tracking-tight text-lg text-white">KapexAI</span>
      </div>

      <div className="flex items-center gap-4">
        {user ? (
          <a
            href="/chat"
            className="px-5 py-2 rounded-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all shadow-lg shadow-blue-600/20"
          >
            Open Workspace →
          </a>
        ) : (
          <a
            href="#auth-center"
            className="px-5 py-2 rounded-full bg-white text-gray-900 hover:bg-gray-100 text-xs font-semibold transition-all shadow-lg shadow-white/10"
          >
            Sign In
          </a>
        )}
      </div>
    </nav>
  )
}
