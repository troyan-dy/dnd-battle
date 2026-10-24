#!/bin/bash
# SessionStart hook for Claude Code cloud sessions: install backend (uv) and
# frontend (npm) dependencies so tests, linters and the type checker work right
# away. Idempotent — re-running only syncs what changed. No-op locally.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Backend: uv installs the Python from backend/.python-version if missing, then
# syncs the locked deps (incl. the dev group: pytest, ruff, mypy,
# wemake-python-styleguide).
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
(cd "$ROOT/backend" && uv sync --frozen)

# Backend style gate: wemake-python-styleguide (flake8, WPS rules; see
# backend/setup.cfg). Report-only so a dirty tree never blocks the session; the
# summary line lands in the session context.
if (cd "$ROOT/backend" && uv run --frozen flake8 . >/dev/null 2>&1); then
  echo "wemake-python-styleguide: backend is clean (cd backend && uv run flake8 .)"
else
  echo "wemake-python-styleguide: violations found — run: cd backend && uv run flake8 ."
fi

# Frontend: `npm install` (not `npm ci`) so the cached node_modules is reused.
(cd "$ROOT/frontend" && npm install --no-audit --no-fund)
