import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// React + Vite. three (with its examples/jsm addons) is pinned to 0.143.0 so the
// ported planet scene runs against the exact API it was authored on.
export default defineConfig({
  plugins: [react()],
  server: { port: 3000, host: true },
})
