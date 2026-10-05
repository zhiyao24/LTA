export function apiBaseUrl(configured: string | undefined): string {
  const value = configured?.trim() || '/'
  // Empty prefix makes /api/... requests stay on the same HTTPS origin.
  if (value === '/') return ''
  const url = new URL(value)
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('VITE_API_BASE_URL must be / or an HTTP(S) base URL without credentials, query or fragment.')
  }
  return value.replace(/\/$/, '')
}
