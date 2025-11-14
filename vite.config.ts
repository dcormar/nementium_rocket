import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',          // 🔹 permite acceso desde fuera del host (Docker, LAN, etc.)
    port: 5173,               // 🔹 puerto de desarrollo
    strictPort: true,         // evita que Vite cambie el puerto automáticamente
    allowedHosts: ['host.docker.internal'],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // tu backend local (FastAPI, Express, etc.)
        changeOrigin: true,
        secure: false,
      },
    },
  },
})