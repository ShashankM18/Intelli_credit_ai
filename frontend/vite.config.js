import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/pipeline': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/analysis': 'http://localhost:8000',
      '/research': 'http://localhost:8000',
      '/report': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
    },
  },
})
