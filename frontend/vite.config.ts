import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: path.resolve(rootDir, '../frontend_dist'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1400,
  },
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/libraries': 'http://127.0.0.1:8000',
      '/episodes': 'http://127.0.0.1:8000',
      '/channels': 'http://127.0.0.1:8000',
      '/bench': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/scenarios': 'http://127.0.0.1:8000',
      '/replay': 'http://127.0.0.1:8000',
      '/docs': 'http://127.0.0.1:8000',
    },
  },
})
