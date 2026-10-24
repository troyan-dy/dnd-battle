#!/usr/bin/env bash
# Run the full backend lint gate (the same checks as CI's backend job, minus tests).
#
# Usage (from repo root or backend/):
#   ./backend/scripts/lint.sh
#
#   ruff check            lint (pycodestyle / pyflakes / isort / bugbear / ...)
#   ruff format --check   formatting
#   mypy                  strict type checking
#   flake8                wemake-python-styleguide (WPS rules only, see setup.cfg)

set -euo pipefail

cd "$(dirname "$0")/.."

uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run flake8 .
