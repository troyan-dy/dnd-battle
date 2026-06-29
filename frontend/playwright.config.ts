import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

// End-to-end harness for the core real-time guarantee (CLAUDE.md): two separate
// browser clients in the same room, one moves a token, the other sees it. Playwright
// boots BOTH servers itself so the suite is self-contained:
//   - the FastAPI + Socket.IO backend on :8000 (its sqlite default — no Postgres),
//     pointed at a throwaway DB + map dir so a run never touches dev data;
//   - the Vite dev server on :5173 (the app's default API/socket origin) built with
//     VITE_E2E=1 so the board exposes the real token-move path for the test driver.
// Only chromium is installed in this environment, so we run a single chromium project.

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..');
const backendDir = resolve(repoRoot, 'backend');
// Throwaway sqlite DB + map storage so e2e never mutates the developer's dnd_battle.db.
const e2eDbPath = resolve(backendDir, 'e2e_dnd_battle.db');
const e2eMapDir = resolve(backendDir, 'var', 'e2e_map_uploads');

const FRONTEND_URL = 'http://127.0.0.1:5173';
// Port 8100 (not the conventional 8000) to dodge a Docker-published :8000 that is a
// common collision on dev machines; the SPA is pointed here via VITE_API_BASE_URL.
const BACKEND_PORT = 8100;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: FRONTEND_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Authoritative server: REST API + /socket.io, on its zero-infra sqlite default.
      // Create the throwaway DB schema (alembic, reads DATABASE_URL from env) before
      // serving so the room-seeding REST calls have tables to write to.
      command:
        '.venv/bin/alembic upgrade head && ' +
        `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT} --log-level warning`,
      cwd: backendDir,
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        DATABASE_URL: `sqlite+aiosqlite:///${e2eDbPath}`,
        MAP_STORAGE_DIR: e2eMapDir,
        APP_BASE_URL: FRONTEND_URL,
        SOCKETIO_CORS_ORIGINS: FRONTEND_URL,
      },
    },
    {
      // The SPA, built with the e2e move hook enabled (compiled out of normal builds).
      command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
      cwd: here,
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VITE_E2E: '1',
        // Same-origin: the SPA uses relative URLs (API + socket) and Vite proxies
        // them to the backend, sidestepping the REST API's lack of CORS in the
        // browser. Node-side seeding in the spec still hits the backend directly.
        VITE_API_BASE_URL: '',
        E2E_BACKEND_URL: BACKEND_URL,
      },
    },
  ],
});
