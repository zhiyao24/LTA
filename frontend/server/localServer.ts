import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createSecureContext } from 'node:tls'
import type { ServerOptions } from 'vite'

export function localServerOptions(env: Record<string, string>, frontendRoot: string): ServerOptions {
  const tls = env.FRONTEND_HTTPS === 'true'
  if (env.FRONTEND_HTTPS && !['true', 'false'].includes(env.FRONTEND_HTTPS)) {
    throw new Error('FRONTEND_HTTPS must be true or false.')
  }
  const backendPort = env.LTA_BACKEND_PORT || '8000'
  if (!/^\d+$/.test(backendPort) || +backendPort < 1 || +backendPort > 65535) {
    throw new Error('LTA_BACKEND_PORT must be a port from 1 to 65535.')
  }
  let https: ServerOptions['https']
  if (tls) {
    try {
      https = {
        cert: readFileSync(resolve(frontendRoot, '../.local-https/server.crt')),
        key: readFileSync(resolve(frontendRoot, '../.local-https/server.key')),
        minVersion: 'TLSv1.2',
      }
      createSecureContext(https)
    } catch {
      throw new Error('HTTPS certificates are missing or invalid. Run scripts/setup-https.sh with the Mac Wi-Fi IP first. HTTPS will not fall back to HTTP.')
    }
  }
  // Browser -> this origin -> loopback FastAPI. Never forward API tokens over LAN HTTP.
  const target = `http://127.0.0.1:${backendPort}`
  return {
    host: '0.0.0.0', port: tls ? 5443 : 5173, strictPort: true,
    https, cors: false,
    fs: { strict: true, allow: [frontendRoot] },
    proxy: Object.fromEntries(['^/api(?:/|$)', '^/health$', '^/docs(?:/|$)', '^/openapi\\.json$']
      .map((path) => [path, { target, changeOrigin: true, timeout: 15000, proxyTimeout: 15000 }])),
  }
}
