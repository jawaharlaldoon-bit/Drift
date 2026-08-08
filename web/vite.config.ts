import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    restoreMocks: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/v1': 'http://localhost:8080',
      '/healthz': 'http://localhost:8080',
    },
  },
})
