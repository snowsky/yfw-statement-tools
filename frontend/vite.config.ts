import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const isSidecar = process.env.VITE_MODE === 'sidecar'

export default defineConfig({
  plugins: [react()],
  // In sidecar mode the UI is served at /plugins/statement-tools/ by the main nginx.
  // Setting base makes Vite emit /plugins/statement-tools/assets/... URLs so the
  // browser fetches assets through the correct nginx proxy path.
  base: isSidecar ? '/plugins/statement-tools/' : '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
