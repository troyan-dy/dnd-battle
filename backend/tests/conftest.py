"""Shared pytest fixtures: a fresh in-memory database and an ASGI client wired to it.

Every test gets its own in-memory sqlite schema (no Postgres needed). API tests
drive the real FastAPI app through ``httpx.ASGITransport`` with ``get_session``
overridden to use that database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import partial

import httpx
import pytest_asyncio
from app.db.session import get_session
from app.main import create_app
from app.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.support import ClientFactory, SessionMaker


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[SessionMaker]:
    """A session factory bound to a fresh in-memory sqlite schema."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _session_from(factory: SessionMaker) -> AsyncIterator[AsyncSession]:
    """The ``get_session`` override: a request-scoped session from ``factory``."""
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client_and_factory(factory: SessionMaker) -> AsyncIterator[ClientFactory]:
    """Yield an ASGI client wired to the in-memory DB plus its session factory."""
    app = create_app()
    app.dependency_overrides[get_session] = partial(_session_from, factory)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory


@pytest_asyncio.fixture
async def client(client_and_factory: ClientFactory) -> httpx.AsyncClient:
    """Just the ASGI client of :func:`client_and_factory`."""
    return client_and_factory[0]
