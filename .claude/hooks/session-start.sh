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
# syncs the locked deps (incl. the dev group: pytest, ruff, mypy).
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
(cd "$ROOT/backend" && uv sync --frozen)

# Frontend: `npm install` (not `npm ci`) so the cached node_modules is reused.
(cd "$ROOT/frontend" && npm install --no-audit --no-fund)
