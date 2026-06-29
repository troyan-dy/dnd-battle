# STATE.md — Handoff Log

> The orchestrator reads this FIRST each cycle, then ROADMAP.md.
> Each agent appends a short entry. Keep it terse. Newest at the top.

## CURRENT FOCUS
Phase 0 — Foundation. Lint/format wired for both packages (backend ruff+mypy strict; frontend prettier + existing oxlint) & ticked.
Next: "CI script that runs lint + tests for both packages" (last Phase 0 task).

## NEEDS HUMAN
<!-- Agents put blocking questions here and STOP instead of guessing. -->
- (none yet)

## LOG
<!-- Format: [date] [agent] — what changed · what's next -->
- [2026-06-29] orchestrator — Lint/format wired both packages. Backend: added `ruff>=0.8` + `mypy>=1.13` dev deps and `[tool.ruff]` (line-length 100, py312, select E/W/F/I/UP/B/C4/SIM/RUF) + `[tool.mypy]` (strict, files app+tests, relaxed decorators for tests) to pyproject; `uv sync`; ruff autofixed one import-sort in test_health.py → `ruff check`/`ruff format --check` clean, `mypy` strict clean, pytest 2 passed. Frontend: added `prettier@^3` dev dep + `.prettierrc.json` (singleQuote, semi, trailingComma=all, printWidth 100) + `.prettierignore`; `format`/`format:check` scripts; ran `npm run format` → `format:check` clean, oxlint clean, build clean, vitest 1 passed. Decision: kept oxlint (ESLint-family, already wired & green) as the linter instead of adding ESLint to avoid duplicate/conflicting linters; prettier covers formatting. npm install needed public registry (sandbox-gated) · next: CI script (lint+tests both packages).
- [2026-06-29] implementer — Added root `docker-compose.yml` (postgres:16 default w/ named volume `dnd_pgdata` + pg_isready healthcheck; redis:7 gated behind `profiles: [cache]` w/ healthcheck) and root `.env.example` (POSTGRES_*, asyncpg `DATABASE_URL`, `REDIS_URL`; `.env` already gitignored). No app/DB code touched. Validated YAML structure + env vars via uv python (postgres has no profile so it's default-up; redis profile=[cache]; DATABASE_URL uses postgresql+asyncpg://) → ALL OK. `docker compose config` not runnable in sandbox (approval-gated) so used programmatic schema/env validation instead · next: ruff+mypy / eslint+prettier.
- [2026-06-29] implementer — Wired Vitest (jsdom + Testing Library + jest-dom); added `src/App.test.tsx` smoke test + `src/setupTests.ts`; `test`/`test:watch` scripts. Test config lives in standalone `vitest.config.ts` (Vitest's nested Vite plugin types clash with project Vite 8/rolldown, so kept out of `tsc -b`). Deps fetched from public npm registry (private artifactory was unreachable). `npm run test` → 1 passed, `npm run build` clean, `npm run lint` clean · next: docker-compose Postgres + `.env.example`.
- [2026-06-29] orchestrator — Verified pytest + pytest-asyncio wired (`asyncio_mode=auto`, dev deps fastapi/httpx); `uv run pytest -q` → 2 passed (incl. /health ASGITransport smoke test). DoD met, ticked · next: frontend Vite boot + Vitest smoke test.
- [2026-06-29] orchestrator — Verified Backend uv project + FastAPI `/health` + `scripts/run.sh` (executable); `uv run pytest` → 2 passed. DoD met, ticked · next: pytest smoke-test task (likely already green) then frontend Vitest smoke.
- [2026-06-29] implementer — Scaffolded monorepo: restored `/backend` (FastAPI app factory, `/health`, pytest) and `/frontend` (Vite+React+TS) from known-good history; `uv run pytest` → 2 passed · next: backend uv project + `/health` + run script task.
- [INIT] host — Repo initialized with Claude Code agent setup. Begin Phase 0.
