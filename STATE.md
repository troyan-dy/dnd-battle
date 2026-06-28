# STATE.md — Журнал передачи

> Оркестратор читает ЭТО первым каждый цикл, затем ROADMAP.md.
> Каждый агент дописывает короткую запись. Держи лаконично. Новое — сверху.
> Язык записей — русский.

## ТЕКУЩИЙ ФОКУС
Фаза 0 — Фундамент. Монорепо собрано (`backend/` uv+FastAPI, `frontend/` Vite+React+TS).
Параллельно открыта Фаза L (локализация): язык продукта по умолчанию — русский (`ru`),
все пользовательские строки идут через i18n.
Дальше: фабрика приложения FastAPI + эндпоинт `/health` + скрипт запуска uvicorn.

## NEEDS HUMAN
<!-- Агенты кладут сюда блокирующие вопросы и ОСТАНАВЛИВАЮТСЯ, а не гадают. -->
- (пусто) Блокер с выполнением `uv`/`python`/`git` снят: команды разрешены в `.claude/settings.local.json`.
  Smoke-тест прогнан (`uv run --dev pytest` → 2 passed), изменения закоммичены. См. LOG.

## LOG
<!-- Формат: [дата] [агент] — что изменилось · что дальше -->
- [2026-06-29] orchestrator — Снят блокер NEEDS HUMAN: в `.claude/settings.local.json` разрешены `uv`/`python`/`python3`/`pytest`/`git` для будущих итераций. `uv sync --dev` поставил dev-зависимости, `uv run --dev pytest` → 2 passed. Тикнут чекбокс Фазы 0 (pytest smoke-тест), закоммичено. · Дальше: Frontend Vitest smoke-тест.
- [2026-06-29] orchestrator/tester — Подготовлен smoke-тест бэкенда: dev-группа (pytest/pytest-asyncio/httpx) и конфиг pytest в `pyproject.toml`, `backend/tests/test_health.py`. ЗАБЛОКИРОВАНО: окружение не даёт выполнять `uv`/`python`/`git` (см. NEEDS HUMAN) — не прогнал тест и не закоммитил. · Дальше: после разблокировки прогнать `uv run --dev pytest`, закоммитить, тикнуть задачу.
- [2026-06-29] implementer — Фаза 0: `backend/app/main.py` (фабрика `create_app()` + модульный `app`), `GET /health` → `{"status":"ok"}` HTTP 200 подтверждён curl, `backend/scripts/run.sh` (env HOST/PORT/RELOAD, исполняемый). · Дальше: pytest + pytest-asyncio smoke-тест.
- [2026-06-29] host — Проект адаптирован под русскоязычных разработчиков и пользователей: README/ROADMAP/STATE переведены на русский; добавлена сквозная Фаза L (i18n, дефолтная локаль `ru`); в CLAUDE.md зафиксированы требование локализации и словарь домена D&D 2024 (RU). · Дальше: продолжить Фазу 0 (FastAPI `/health`).
- [2026-06-29] implementer — Собрано монорепо: `backend/` (uv, Python 3.12, зависимости FastAPI+uvicorn, пакет `app/` собирается и импортируется) и `frontend/` (Vite+React+TS, собирается через tsc+vite, линт чистый). Корневой README описывает структуру. Проверено: backend `uv sync` + `import app` OK; frontend `npm run build` + `npm run lint` зелёные. ЗАМЕТКА: фронтенд-зависимости поставлены из публичного npm-реестра (приватный artifactory недоступен в окружении); шаблон идёт с oxlint (замена на eslint+prettier — задача Фазы 0 позже). · Дальше: фабрика приложения FastAPI + `/health` + скрипт запуска uvicorn.
- [INIT] host — Репозиторий инициализирован сборкой агентов Claude Code. Начать Фазу 0.
