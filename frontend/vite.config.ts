import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
//
// In e2e mode (VITE_E2E=1, set by the Playwright harness) the SPA talks to the
// backend SAME-ORIGIN via a dev proxy instead of a cross-origin absolute URL: the
// REST API has no CORS middleware, so a cross-origin browser fetch is blocked. The
// proxy forwards the API + realtime paths to the backend (E2E_BACKEND_URL), which
// keeps the e2e harness self-contained without changing production/server code.
// Normal dev/build is unaffected (no proxy unless VITE_E2E is set).
export default defineConfig(() => {
  const e2e = process.env.VITE_E2E === '1';
  const backend = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8100';

  return {
    plugins: [react()],
    server: e2e
      ? {
          proxy: {
            '/rooms': { target: backend, changeOrigin: true },
            '/invites': { target: backend, changeOrigin: true },
            '/health': { target: backend, changeOrigin: true },
            '/socket.io': { target: backend, changeOrigin: true, ws: true },
          },
        }
      : undefined,
  };
});
