# STATE.md — Handoff Log

> The orchestrator reads this FIRST each cycle, then ROADMAP.md.
> Each agent appends a short entry. Keep it terse. Newest at the top.

## CURRENT FOCUS
Phase 0 — Foundation. Frontend Vitest wired & ticked (`npm run test` → 1 passed; build + lint clean).
Next: "Docker-compose for Postgres (+ optional Redis); `.env.example`".

## NEEDS HUMAN
<!-- Agents put blocking questions here and STOP instead of guessing. -->
- (none yet)

## LOG
<!-- Format: [date] [agent] — what changed · what's next -->
- [2026-06-29] implementer — Wired Vitest (jsdom + Testing Library + jest-dom); added `src/App.test.tsx` smoke test + `src/setupTests.ts`; `test`/`test:watch` scripts. Test config lives in standalone `vitest.config.ts` (Vitest's nested Vite plugin types clash with project Vite 8/rolldown, so kept out of `tsc -b`). Deps fetched from public npm registry (private artifactory was unreachable). `npm run test` → 1 passed, `npm run build` clean, `npm run lint` clean · next: docker-compose Postgres + `.env.example`.
- [2026-06-29] orchestrator — Verified pytest + pytest-asyncio wired (`asyncio_mode=auto`, dev deps fastapi/httpx); `uv run pytest -q` → 2 passed (incl. /health ASGITransport smoke test). DoD met, ticked · next: frontend Vite boot + Vitest smoke test.
- [2026-06-29] orchestrator — Verified Backend uv project + FastAPI `/health` + `scripts/run.sh` (executable); `uv run pytest` → 2 passed. DoD met, ticked · next: pytest smoke-test task (likely already green) then frontend Vitest smoke.
- [2026-06-29] implementer — Scaffolded monorepo: restored `/backend` (FastAPI app factory, `/health`, pytest) and `/frontend` (Vite+React+TS) from known-good history; `uv run pytest` → 2 passed · next: backend uv project + `/health` + run script task.
- [INIT] host — Repo initialized with Claude Code agent setup. Begin Phase 0.
