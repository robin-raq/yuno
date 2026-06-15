import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Load repo-root .env so VITE_* / BACKEND_PORT stay in sync with make dev
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const apiTarget =
    env.VITE_API_TARGET ||
    `http://localhost:${env.BACKEND_PORT || '8001'}`

  return {
    plugins: [react()],
    envDir: path.resolve(__dirname, '..'),
    server: {
      port: 5173,
      proxy: {
        '/agents': apiTarget,
        '/runs': apiTarget,
        '/workflows': apiTarget,
        '/events': apiTarget,
        '/health': apiTarget,
      },
    },
  }
})
