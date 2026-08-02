import { GoogleOAuthProvider } from '@react-oauth/google'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/global.css'

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

if (!clientId) {
  throw new Error('VITE_GOOGLE_CLIENT_ID is missing. Copy .env.example to .env.local and add your Google client ID.')
}

createRoot(document.getElementById('root')!).render(
  <GoogleOAuthProvider clientId={clientId}>
    <App />
  </GoogleOAuthProvider>,
)
