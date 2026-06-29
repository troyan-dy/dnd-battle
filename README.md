# D&D Battler — autonomous Claude Code setup

A drop-in setup that makes Claude Code work a project forward continuously, using
role-based subagents and a roadmap as the source of truth.

## What's here
```
CLAUDE.md                  # project context every agent reads (EDIT the STACK note if needed)
ROADMAP.md                 # what to build, in phases — the source of truth
STATE.md                   # handoff log: what just happened, what's next, blockers
run-loop.sh                # the continuous loop (headless)
.claude/
  settings.json            # optional Stop/SubagentStop hooks (verify schema in docs)
  agents/
    orchestrator.md        # coordinator (main-thread agent)
    pm.md                  # spec + acceptance criteria
    architect.md           # data model, realtime protocol, security decisions
    implementer.md         # writes code + tests
    tester.md             # tests, esp. multiplayer sync correctness
    reviewer.md            # read-only quality/security gate
```

## Install
1. Install Claude Code and sign in. Verify the version supports subagents:
   `claude --version`  (see docs.claude.com/en/docs/claude-code).
2. Copy these files into the ROOT of your project repo (keep the `.claude/` path).
3. `git init` if you haven't — the loop relies on git for checkpoints/audit.
4. Open `CLAUDE.md` and adjust the **STACK** note. Backend is fixed (FastAPI);
   tweak the frontend choices if you disagree.
5. `chmod +x run-loop.sh`

## Run
- Interactive first (recommended): open `claude`, then
  `Use the orchestrator agent to run one cycle.` — watch it pick the first task,
  delegate, and update ROADMAP/STATE. Do a few cycles by hand to build trust.
- Continuous:  `./run-loop.sh`
  - It stops automatically when STATE.md has a real **NEEDS HUMAN** entry, when the
    roadmap is fully checked, or after `MAX_CYCLES`.
  - Tune with env vars, e.g. `SLEEP_SECS=60 MAX_CYCLES=50 ./run-loop.sh`.

## Run the app (Docker)
Run the whole thing — Postgres, backend (FastAPI + Socket.IO), and the frontend
(SPA served by nginx, which reverse-proxies the API + realtime so it's all one
origin) — with one command:

```bash
cp .env.example .env          # optional; sensible defaults work out of the box
docker compose up --build
```

Then open **http://localhost:8080**. The backend migrates the database on start.
Postgres data and uploaded maps persist in a local **`./.docker-data/`** folder
in the project (git-ignored), so the data lives with the repo and survives
restarts.

- Change the port if 8080 is taken: `APP_PORT=8090 APP_BASE_URL=http://localhost:8090 docker compose up --build` (keep both in sync — `APP_BASE_URL` is baked into invite links and the realtime CORS allowlist).
- Just the infra (to run the backend on your host instead): `docker compose up postgres`.
- Optional Redis (only when scaling past one server process): `docker compose --profile cache up`.
- Tear down: `docker compose down`. To also wipe the data, delete the local folder: `rm -rf ./.docker-data`.

## How it stays sane
- One task per cycle, each a small reviewable commit → `git log` is your audit trail.
- The orchestrator never invents architecture; risky areas (auth, invite-link
  security, sync protocol) require the architect agent first.
- Agents stop and ask (via STATE.md → NEEDS HUMAN) instead of guessing.

## Reality check
Running for hours/days costs real tokens and hits rate limits — budget for it.
Check the diff regularly; autonomous loops drift. Treat phase boundaries as natural
points to review before letting it continue.
