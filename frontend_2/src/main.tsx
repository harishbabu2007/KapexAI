import { GoogleOAuthProvider } from '@react-oauth/google'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './lib/auth'
import './styles/global.css'
import './styles/chat.css'

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

if (!clientId) {
  throw new Error('VITE_GOOGLE_CLIENT_ID is missing. Copy .env.example to .env.local and add your Google client ID.')
}

createRoot(document.getElementById('root')!).render(
  <GoogleOAuthProvider clientId={clientId}>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </GoogleOAuthProvider>,
)
