import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath } from 'node:url'
import { localServerOptions } from './server/localServer.ts'

// https://vite.dev/config/
export default defineConfig(({ mode, command }) => {
  const root = fileURLToPath(new URL('.', import.meta.url))
  const env = { ...loadEnv(mode, root, ''), ...process.env } as Record<string, string>
  return {
    plugins: [react()],
    // HTTPS must never use a stale absolute HTTP backend URL from a local env file.
    define: env.FRONTEND_HTTPS === 'true' ? { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/') } : {},
    server: command === 'serve' ? localServerOptions(env, root) : undefined,
  }
})
