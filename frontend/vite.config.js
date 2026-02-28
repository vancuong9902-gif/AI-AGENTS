import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api -> backend container to avoid browser CORS issues in Docker.
// Browser calls: http://localhost:5173/api/...
// Vite dev server (inside container) forwards to: http://backend:8000/api/...
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
