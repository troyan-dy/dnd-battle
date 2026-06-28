# CLAUDE.md — Project Context

> Этот файл читают ВСЕ агенты. Здесь живёт «правда» о проекте.
> ⚠️ Поправь раздел STACK под себя — остальное менять не обязательно.

> 🇷🇺 **Проект для русскоязычных разработчиков и пользователей.**
> - Язык продукта по умолчанию — **русский (`ru`)**; весь пользовательский текст идёт через i18n.
> - Документация и журналы (`README.md`, `ROADMAP.md`, `STATE.md`) ведутся на русском.
> - Имена сущностей в КОДЕ остаются английскими (`Room`, `Token`, `Action`…) — единый
>   технический словарь; русские названия из словаря домена ниже — для UI и общения.
> - Термины D&D 2024 в интерфейсе — по-русски (см. «Словарь домена» ниже).

## What we are building

An online D&D combat tool ("battler") — a real-time, multiplayer virtual
tabletop focused on encounters.

- A **host** (DM) creates a **Room**, uploads a **map**, and configures characters.
- Each participant gets a **unique invite link**. The link binds them to the room
  AND to a specific character/token.
- Opening the link shows the shared **board** (map + grid + tokens) plus that
  player's own character panel.
- **Movement, attacks, marks/pings and other board changes are broadcast to
  everyone viewing the board in real time.**
- Rules follow the **latest D&D ruleset (2024 / current Player's Handbook)**.

## STACK  (← EDIT THIS to match your real choices)

Backend is fixed (Python + FastAPI). Frontend is an assumed default — change freely.

- Backend language: **Python 3.12+**
- Backend framework: **FastAPI** (ASGI, served by **uvicorn**), authoritative server state
- Realtime: **python-socketio** (ASGI) mounted on the FastAPI app — gives built-in
  rooms + reconnection; pairs with **socket.io-client** on the frontend.
  (Alternative: native FastAPI `WebSocket` endpoints if you'd rather drop Socket.IO.)
- Backend persistence: **PostgreSQL** via **SQLAlchemy 2.x (async)** + **asyncpg**,
  migrations with **Alembic**. Live BoardState kept in memory per room
  (optionally backed by **Redis** when you scale past one server process).
- Backend package manager: **uv** (pip/poetry also fine)
- Backend tests: **pytest** + **pytest-asyncio**; **httpx** for API tests
- Frontend: **React + Vite + TypeScript**, canvas via **Konva** (react-konva)
- Frontend tests: **Vitest** (unit) + **Playwright** (e2e for multi-client sync)
- Data contracts: **Pydantic** models on the server are the source of truth for
  Action/BoardState shapes; mirror them in TS types on the client.
- Localization (i18n): **i18next + react-i18next** on the frontend, default locale **`ru`**,
  переводы в `frontend/src/locales/ru/*.json` (источник правды). Никаких хардкод-строк в UI.
  Сообщения/ошибки сервера локализуемы (стабильные коды + перевод на клиенте).

## Core domain model (shared vocabulary — use these names in code)

- **Room**: an encounter session. Has an id, a map, a board state, participants.
- **InviteLink**: unique per participant. Resolves to `{ roomId, participantId, characterId }`.
- **Participant**: a connected user. Role is `host` or `player`.
- **Character**: D&D 2024 stat block + HP, conditions, owned by a participant.
- **Token**: the on-board piece for a character. Has `{ x, y }` grid coords, size.
- **BoardState**: authoritative state — tokens, marks, initiative/turn order, fog.
- **Action**: a broadcast event — `move`, `attack`, `mark`, `damage`, `endTurn`, etc.

## Словарь домена (RU ↔ код) — единые переводы для UI и общения

> В коде — английское имя слева. В интерфейсе и в обсуждениях — русское справа.
> Любой новый пользовательский термин сначала добавляй сюда, потом переводи в `locales/ru`.

Сущности:
- `Room` — **Комната** (сессия-столкновение)
- `InviteLink` — **Инвайт-ссылка** (уникальная ссылка-приглашение)
- `Participant` — **Участник** (роли: `host` — **Ведущий/Мастер**, `player` — **Игрок**)
- `Character` — **Персонаж**
- `Token` — **Жетон** (фишка персонажа на доске)
- `BoardState` — **Состояние доски**
- `Action` — **Действие** (бродкаст-событие)
- `map` — **Карта**, `grid` — **Сетка**, `board` — **Доска**, `fog of war` — **Туман войны**

Боевые термины D&D 2024:
- `HP (hit points)` — **Хиты / Очки здоровья**
- `AC (armor class)` — **КЗ (класс защиты)**
- `initiative` — **Инициатива**, `turn order` — **Порядок ходов**, `end turn` — **Завершить ход**
- `attack roll` — **Бросок атаки**, `damage` — **Урон**, `healing` — **Лечение**
- `advantage / disadvantage` — **Преимущество / Помеха**
- `ability score` — **Характеристика**, `modifier` — **Модификатор**, `proficiency bonus` — **Бонус мастерства**
- `condition` — **Состояние**, `resistance` — **Сопротивление**
- `mark / ping` — **Метка / Пинг**, `distance (feet)` — **Дистанция (футы, «фт»)**

## Architecture rules (guardrails for all agents)

1. **Server is authoritative.** Clients send intents; the server validates against
   rules and BoardState, then broadcasts the resulting Action to the room.
2. **Reconnect-safe.** A client that reloads its link must receive full current
   BoardState and resync. Never assume a client saw earlier events.
3. **Permissions.** A `player` may only move/act with their own token; only the
   `host` may move others, edit the map, or reveal fog. Enforce on the SERVER.
4. **Rules engine is isolated.** D&D 2024 logic (attack rolls, damage, conditions)
   lives in its own module with pure functions + unit tests. No rules math in the
   transport or UI layers.
5. **Optimistic UI is allowed but reconciled.** The server's broadcast is the
   source of truth; clients roll back on mismatch.
6. **Локализация обязательна.** Любой пользовательский текст — только через i18n-ключи,
   дефолтная локаль `ru`. Никаких хардкод-строк в UI/сообщениях. Термины D&D 2024 берём
   из «Словаря домена». Это часть Definition of Done.

## Working agreements (how the agent loop operates)

- `ROADMAP.md` is the single source of truth for WHAT to do next.
- `STATE.md` is the handoff log: what just happened, what's next, any blockers.
- **Definition of Done** for any task: code compiles, lint passes, relevant tests
  added and green, `ROADMAP.md` checkbox ticked, `STATE.md` updated. Если задача
  добавляет пользовательский текст — строки идут через i18n и есть русский перевод (`ru`).
- Документы и записи в `STATE.md`/`ROADMAP.md` ведём на русском.
- Small, reviewable commits. One task = one logical commit.
- If a task is ambiguous or risky (auth, data loss, money), STOP and write a
  question into `STATE.md` under "NEEDS HUMAN" instead of guessing.
- Never delete user data or rewrite history without an explicit task saying so.
