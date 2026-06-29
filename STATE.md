# STATE.md — Handoff Log

> The orchestrator reads this FIRST each cycle, then ROADMAP.md.
> Each agent appends a short entry. Keep it terse. Newest at the top.

## CURRENT FOCUS
Phase 0 — Foundation. Backend uv project + FastAPI `/health` + uvicorn run script verified & ticked.
Next: tick/verify "Backend: pytest + pytest-asyncio wired, one passing smoke test"
(test_health already green via httpx ASGITransport), then frontend Vitest smoke test.

## NEEDS HUMAN
<!-- Agents put blocking questions here and STOP instead of guessing. -->
- (none yet)

## LOG
<!-- Format: [date] [agent] — what changed · what's next -->
- [2026-06-29] orchestrator — Verified Backend uv project + FastAPI `/health` + `scripts/run.sh` (executable); `uv run pytest` → 2 passed. DoD met, ticked · next: pytest smoke-test task (likely already green) then frontend Vitest smoke.
- [2026-06-29] implementer — Scaffolded monorepo: restored `/backend` (FastAPI app factory, `/health`, pytest) and `/frontend` (Vite+React+TS) from known-good history; `uv run pytest` → 2 passed · next: backend uv project + `/health` + run script task.
- [INIT] host — Repo initialized with Claude Code agent setup. Begin Phase 0.
