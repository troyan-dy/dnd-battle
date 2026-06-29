# ROADMAP.md — D&D Battler

> Source of truth for WHAT to do next. Agents pick the first unchecked task whose
> dependencies are done. Tick `[x]` when DONE (see Definition of Done in CLAUDE.md).
> Add new ideas to `## Backlog` at the bottom; the host promotes them into phases.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (see STATE.md)

---

## Phase 0 — Foundation
- [x] Scaffold monorepo: `/backend` (FastAPI) and `/frontend` (Vite+React+TS)
- [x] Backend: uv project, FastAPI app, `/health` endpoint, uvicorn run script
- [x] Backend: pytest + pytest-asyncio wired, one passing smoke test
- [x] Frontend: Vite app boots, Vitest wired, one passing smoke test
- [x] Docker-compose for Postgres (+ optional Redis); `.env.example`
- [x] Lint/format: ruff + mypy (backend), eslint + prettier (frontend)
- [x] CI script that runs lint + tests for both packages

## Phase 1 — Rooms & invite links
- [x] Data model: Room, Participant, InviteLink, Character (SQLAlchemy + Alembic)
- [x] API: create room (host) → returns room id + host link
- [x] API: generate per-participant unique invite links bound to a character slot
- [x] API: resolve invite link → `{ roomId, participantId, role, characterId }`
- [x] Link security: unguessable tokens, single-purpose, revocable
- [x] Frontend: host "create room" screen; join screen via link

## Phase 2 — Map & board rendering
- [x] API: host uploads a map image; stored + served
- [x] Frontend: render map on a Konva stage; pan + zoom
- [x] Grid overlay (square grid first), configurable cell size + offset
- [x] Board viewport syncs nothing yet — purely local rendering

## Phase 3 — Characters & tokens
- [x] Character config UI (host): name, portrait, stats, max HP
- [x] Place tokens on the grid; bind each token to a character
- [x] Player view: opening a player link shows board + only their character panel
- [x] Token rendering: name, HP bar, current conditions

## Phase 4 — Realtime sync (the core)
- [ ] python-socketio mounted on FastAPI; client connects via socket.io-client
- [ ] Join room → server sends FULL current BoardState (reconnect-safe)
- [ ] Action protocol (Pydantic): move, mark, damage, endTurn… defined + versioned
- [ ] Server validates intents (permissions + bounds) before broadcasting
- [ ] Broadcast resulting Action to all participants in the room
- [ ] Optimistic move on client + reconcile to server broadcast
- [ ] Reconnect test: reload a player link mid-encounter, state restores

## Phase 5 — Combat actions (visible to all)
- [ ] Move token with grid snapping + distance measurement (feet)
- [ ] Marks / pings on the board (temporary, visible to everyone)
- [ ] Initiative tracker + turn order; "end turn" advances it
- [ ] Apply damage/healing to a token; HP updates broadcast live
- [ ] Basic attack flow: choose target → roll → apply result, all see the log
- [ ] Shared combat log panel

## Phase 6 — D&D 2024 rules engine
- [ ] Isolated rules module (pure functions, fully unit-tested)
- [ ] Ability scores, modifiers, proficiency bonus
- [ ] Attack roll vs AC; advantage/disadvantage
- [ ] Damage rolls + types; basic resistances
- [ ] Conditions (2024 list) with their mechanical effects
- [ ] Wire rules engine into the attack/damage actions from Phase 5

## Phase 7 — Permissions, persistence, polish
- [ ] Server-enforced permissions: player acts only on own token; host can do all
- [ ] Persist room + board snapshots so a session survives a server restart
- [ ] Fog of war / hidden tokens controllable by host
- [ ] Error handling + user-facing messages on desync/disconnect
- [ ] e2e Playwright: two browser clients, one moves → other sees it

---

## Backlog (host promotes into phases)
- [ ] Dice roller with shared results
- [ ] Hex grid option
- [ ] Spell area templates (cone/sphere/line)
- [ ] Mobile/touch controls
- [ ] Reconnect grace + spectator role
