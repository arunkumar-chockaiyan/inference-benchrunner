import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api': process.env.BACKEND_URL || 'http://localhost:8080',
      '/ws': { target: process.env.BACKEND_WS_URL || 'ws://localhost:8080', ws: true },
    },
  },
})
