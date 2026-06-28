#!/usr/bin/env bash
# run-loop.sh — drive the autonomous engineering loop.
#
# Each cycle runs the orchestrator once in headless mode. The orchestrator picks
# ONE roadmap task, delegates it, verifies it, and updates ROADMAP.md / STATE.md.
# The loop stops automatically when a human is needed or the roadmap is done.
#
# Usage:  ./run-loop.sh
# Stop:   Ctrl-C anytime. git log is your audit trail.
#
# Tunables (env vars):
#   MAX_CYCLES   hard cap on iterations         (default 200)
#   SLEEP_SECS   pause between cycles            (default 30)
#   MODEL        model for the orchestrator      (default opus)

set -euo pipefail

MAX_CYCLES="${MAX_CYCLES:-200}"
SLEEP_SECS="${SLEEP_SECS:-30}"
MODEL="${MODEL:-opus}"

cd "$(dirname "$0")"

# Stop if STATE.md has a real entry under "NEEDS HUMAN".
# Placeholders that mean "nothing to do" are ignored: English "(none yet)" and
# Russian "(пока нет)". Comment lines are ignored too.
needs_human() {
  awk '/## NEEDS HUMAN/{f=1;next}/^## /{f=0}f' STATE.md \
    | grep -v '^<!--' | grep -vE '\(none yet\)|\(пока нет\)' | grep -Eq '\S'
}

# Stop if every ROADMAP checkbox is ticked.
roadmap_done() {
  ! grep -Eq '^\s*-\s*\[( |~|!)\]' ROADMAP.md
}

echo "▶ starting loop (max $MAX_CYCLES cycles, ${SLEEP_SECS}s between)"

for ((i=1; i<=MAX_CYCLES; i++)); do
  if needs_human; then
    echo "⏸ cycle $i: human input needed. See STATE.md → NEEDS HUMAN. Stopping."
    exit 0
  fi
  if roadmap_done; then
    echo "✅ roadmap complete. Stopping."
    exit 0
  fi

  echo "──────── cycle $i ────────"

  # Headless run. --agent picks the orchestrator as the main-thread agent.
  # --permission-mode acceptEdits lets it edit files without prompting; review the
  # git diff regularly. Drop it if you want to approve each change manually.
  claude -p "Run one orchestrator cycle as defined in your agent instructions: \
    read STATE.md then ROADMAP.md, pick the next eligible task, delegate, verify \
    Definition of Done, then update ROADMAP.md and STATE.md. Do exactly one task. \
    Complete exactly one task, then commit the changes to master and publish them." \
    --agent orchestrator \
    --model "$MODEL" \
    --permission-mode acceptEdits

  # Optional: auto-commit any stray changes so nothing is lost between cycles.
  if ! git diff --quiet || ! git diff --staged --quiet; then
    git add -A && git commit -m "loop: cycle $i checkpoint" --no-verify || true
  fi

  sleep "$SLEEP_SECS"
done

echo "■ reached MAX_CYCLES ($MAX_CYCLES). Stopping."
