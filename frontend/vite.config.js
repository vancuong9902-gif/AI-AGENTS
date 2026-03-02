import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_ORIGIN || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
