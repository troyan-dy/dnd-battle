# syntax=docker/dockerfile:1
#
# Backend image: FastAPI + Socket.IO served by uvicorn, deps managed by uv
# (the repo's package manager). On start it runs Alembic migrations against the
# configured DATABASE_URL, then serves the REST API and the realtime endpoint
# from one process (see app/main.py).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached unless the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code, then install the project itself into the environment.
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Migrate to head, then serve. `exec` so uvicorn becomes PID 1 and receives signals.
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
