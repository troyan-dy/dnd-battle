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
- [x] python-socketio mounted on FastAPI; client connects via socket.io-client
- [x] Join room → server sends FULL current BoardState (reconnect-safe)
- [x] Action protocol (Pydantic): move, mark, damage, endTurn… defined + versioned
- [x] Server validates intents (permissions + bounds) before broadcasting
- [x] Broadcast resulting Action to all participants in the room
- [x] Optimistic move on client + reconcile to server broadcast
- [x] Reconnect test: reload a player link mid-encounter, state restores

## Phase 5 — Combat actions (visible to all)
- [x] Move token with grid snapping + distance measurement (feet)
- [x] Marks / pings on the board (temporary, visible to everyone)
- [x] Initiative tracker + turn order; "end turn" advances it
- [x] Apply damage/healing to a token; HP updates broadcast live
- [x] Basic attack flow: choose target → roll → apply result, all see the log
- [x] Shared combat log panel

## Phase 6 — D&D 2024 rules engine
- [x] Isolated rules module (pure functions, fully unit-tested)
- [x] Ability scores, modifiers, proficiency bonus
- [x] Attack roll vs AC; advantage/disadvantage
- [x] Damage rolls + types; basic resistances
- [x] Conditions (2024 list) with their mechanical effects
- [x] Wire rules engine into the attack/damage actions from Phase 5

## Phase 7 — Permissions, persistence, polish
- [x] Server-enforced permissions: player acts only on own token; host can do all
- [x] Persist room + board snapshots so a session survives a server restart
- [x] Fog of war / hidden tokens controllable by host
- [x] Error handling + user-facing messages on desync/disconnect
- [ ] e2e Playwright: two browser clients, one moves → other sees it

---

## Backlog (host promotes into phases)
- [ ] Dice roller with shared results
- [ ] Hex grid option
- [ ] Spell area templates (cone/sphere/line)
- [ ] Mobile/touch controls
- [ ] Reconnect grace + spectator role
- [ ] Fog of war v2: a HIDDEN creature attacking a VISIBLE player token is currently
      suppressed from that player entirely (their HP reflects only on the next
      BoardState resync, not live). Refine so a player sees damage to their OWN token
      without revealing the hidden attacker. Also: per-player own-character inclusion
      if a host ever hides a player's own token (today the player-filtered BoardState
      is role-uniform, so a hidden own-token drops from that player's board view).
- [ ] Host-only auth gate on HTTP room-CONFIG endpoints (place/update token, set
      initiative, add player, upload map, revoke links) — currently unguarded.
      NEEDS ARCHITECT + human sign-off: introduces HTTP authentication (reuse the
      invite token as a `Authorization: Bearer` credential, assert role=host + room
      match → 401/403) AND requires deciding how the host client persists/transmits
      its secret token across navigation (e.g. the CharacterConfig route holds no
      token). Touches auth + invite-link security → do not implement without sign-off.
