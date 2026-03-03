import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET || 'http://backend:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    hmr: {
      protocol: process.env.VITE_HMR_PROTOCOL || 'ws',
      host: process.env.VITE_HMR_HOST || 'localhost',
      clientPort: Number(process.env.VITE_HMR_CLIENT_PORT || 5173),
    },
    proxy: {
      '/api': {
        target: backendProxyTarget,
        changeOrigin: true,
        ws: true,
      }
    }
  }
})
