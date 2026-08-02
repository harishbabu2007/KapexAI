# KapexAI frontend

React + TypeScript landing page and Google sign-in client.

## Run locally

1. Install Node.js 20 LTS or newer.
2. Copy `.env.example` to `.env.local` and set `VITE_GOOGLE_CLIENT_ID`.
3. Run `npm install` and then `npm run dev`.
4. Open `http://localhost:3000`.

The FastAPI service must run at `http://localhost:8000` (or set `VITE_API_BASE_URL`). Its `.env` needs the same Google client ID and a strong `JWT_SECRET`; see the repository-root `.env.example`.

## Structure

- `src/App.tsx` — landing-page UI and sign-in state
- `src/lib/api.ts` — all HTTP calls to FastAPI
- `src/styles/global.css` — responsive styling
- `.env.example` — safe environment-variable template
