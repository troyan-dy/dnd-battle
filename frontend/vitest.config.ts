import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Standalone Vitest config. Kept separate from vite.config.ts because Vitest
// ships its own nested Vite, whose plugin types clash with the project's Vite 8
// (rolldown) at build time. This file is intentionally excluded from `tsc -b`.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: false,
  },
});
