"""Async SQLAlchemy engine + session factory and a FastAPI dependency.

The engine is created lazily from :data:`app.config.DATABASE_URL`. Routers obtain
a session via the :func:`get_session` dependency; the rules/transport layers never
touch the DB directly (see CLAUDE.md architecture rules).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import DATABASE_URL

engine: AsyncEngine = create_async_engine(DATABASE_URL, future=True)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped :class:`AsyncSession` (FastAPI dependency)."""
    async with async_session_factory() as session:
        yield session
