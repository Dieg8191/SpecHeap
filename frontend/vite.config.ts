import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The production build is written straight into the Python package so that
// `specheap serve` (and the wheel) can host it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/specheap/web/static',
    emptyOutDir: true,
  },
  server: {
    // During development, `npm run dev` proxies the API to `specheap serve`.
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
