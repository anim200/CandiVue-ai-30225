import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // Development server (npm run dev). Port 5173 is the address the backend
  // allows in CORS_ORIGINS. /api is forwarded to the backend, just like
  // nginx does in Docker, so the code always calls /api/... directly.
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
