import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/agents': 'http://localhost:8000',
      '/runs': 'http://localhost:8000',
      '/workflows': 'http://localhost:8000',
      '/events': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
