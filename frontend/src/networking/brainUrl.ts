const LOCAL_BRAIN_URL = 'ws://127.0.0.1:8765'
const DEPLOYED_BRAIN_URL = 'wss://fruitflycapital.onrender.com'

/**
 * Keep local development pointed at the local adapter, but let a deployed
 * build reach the persistent Render websocket when Vercel has no Vite env
 * variable configured. The endpoint contains no credentials.
 */
export function resolveBrainWebSocketUrl(configured: string | undefined) {
  const explicit = configured?.trim()
  if (explicit) return explicit
  const host = window.location.hostname
  const isLocal = host === 'localhost' || host === '127.0.0.1' || host === '[::1]'
  return isLocal ? LOCAL_BRAIN_URL : DEPLOYED_BRAIN_URL
}
