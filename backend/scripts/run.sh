#!/usr/bin/env bash
# Run the D&D battler backend with uvicorn.
#
# Usage (from repo root or backend/):
#   ./backend/scripts/run.sh
#
# Environment variables (all optional, shown with defaults):
#   HOST=0.0.0.0  PORT=8000  RELOAD=true
#
# For production set RELOAD=false (or unset) and supply HOST/PORT via env.

set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

RELOAD_FLAG=""
if [ "${RELOAD}" = "true" ]; then
    RELOAD_FLAG="--reload"
fi

# Run inside the uv-managed virtual environment so no manual activation needed.
exec uv run uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    ${RELOAD_FLAG}
