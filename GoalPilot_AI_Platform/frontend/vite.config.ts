import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend is a separate FastAPI process. "/api" is proxied to it in development so
// that a relative VITE_API_BASE_URL also works; the default env value points straight at
// the backend origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
