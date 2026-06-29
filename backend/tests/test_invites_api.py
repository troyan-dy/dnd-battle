"""API tests for GET /invites/{token} (resolve invite link -> binding).

Runs against a fresh in-memory sqlite schema with get_session overridden, so no
Postgres is needed. Drives the real ASGI app via httpx.ASGITransport.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from app.db.session import get_session
from app.main import create_app
from app.models import (
    Base,
    InviteLink,
    ParticipantRole,
)
from app.security.tokens import hash_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

ClientFactory = tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]


@pytest_asyncio.fixture
async def client_and_factory() -> AsyncIterator[ClientFactory]:
    """Yield an ASGI client wired to a fresh in-memory DB plus its session factory."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory

    await engine.dispose()


async def _create_room(client: httpx.AsyncClient, name: str = "Room") -> dict[str, Any]:
    """Helper: create a room, returning the full create-room response body."""
    resp = await client.post("/rooms", json={"name": name})
    assert resp.status_code == 201
    body: dict[str, Any] = resp.json()
    return body


async def _add_player(client: httpx.AsyncClient, room_id: str) -> dict[str, Any]:
    """Helper: add a player to a room, returning the add-player response body."""
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Aria", "max_hp": 24, "display_name": "P1"},
    )
    assert resp.status_code == 201
    body: dict[str, Any] = resp.json()
    return body


async def _link_for_token(factory: async_sessionmaker[AsyncSession], token: str) -> InviteLink:
    """Fetch the InviteLink row for a plaintext token (test-side, by hash)."""
    async with factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(token))
            )
        ).scalar_one()
        return link


@pytest.mark.asyncio
async def test_resolve_host_link(client_and_factory: ClientFactory) -> None:
    """A host token resolves to the host participant with no character."""
    client, _ = client_and_factory
    room = await _create_room(client, "Goblin Ambush")
    token = room["host_link"]["token"]

    resp = await client.get(f"/invites/{token}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["room_id"] == room["room"]["id"]
    assert body["participant_id"] == room["host_participant_id"]
    assert body["role"] == ParticipantRole.host.value
    assert body["character_id"] is None


@pytest.mark.asyncio
async def test_resolve_player_link_binds_character(
    client_and_factory: ClientFactory,
) -> None:
    """A player token resolves to that player + their bound character slot."""
    client, _ = client_and_factory
    room = await _create_room(client)
    player = await _add_player(client, room["room"]["id"])
    token = player["invite_link"]["token"]

    resp = await client.get(f"/invites/{token}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["room_id"] == room["room"]["id"]
    assert body["participant_id"] == player["participant_id"]
    assert body["role"] == ParticipantRole.player.value
    assert body["character_id"] == player["character_id"]


@pytest.mark.asyncio
async def test_resolve_is_idempotent_and_does_not_consume(
    client_and_factory: ClientFactory,
) -> None:
    """Resolving twice returns the same binding and never sets used_at (reconnect-safe)."""
    client, factory = client_and_factory
    room = await _create_room(client)
    token = room["host_link"]["token"]

    first = (await client.get(f"/invites/{token}")).json()
    second = (await client.get(f"/invites/{token}")).json()
    assert first == second

    link = await _link_for_token(factory, token)
    assert link.used_at is None


@pytest.mark.asyncio
async def test_resolve_unknown_token_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """An unknown token yields the uniform 404 (no enumeration oracle)."""
    client, _ = client_and_factory
    resp = await client.get("/invites/not-a-real-token")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invalid or expired invite link."


@pytest.mark.asyncio
async def test_resolve_revoked_token_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """A revoked link is not resolvable and returns the same uniform 404."""
    client, factory = client_and_factory
    room = await _create_room(client)
    token = room["host_link"]["token"]

    async with factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(token))
            )
        ).scalar_one()
        link.revoked_at = dt.datetime.now(dt.UTC)
        await session.commit()

    resp = await client.get(f"/invites/{token}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invalid or expired invite link."


@pytest.mark.asyncio
async def test_resolve_expired_token_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """A link past its expires_at is not resolvable (uniform 404)."""
    client, factory = client_and_factory
    room = await _create_room(client)
    token = room["host_link"]["token"]

    async with factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(token))
            )
        ).scalar_one()
        link.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        await session.commit()

    resp = await client.get(f"/invites/{token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_future_expiry_still_active(
    client_and_factory: ClientFactory,
) -> None:
    """A link with a future expires_at still resolves successfully."""
    client, factory = client_and_factory
    room = await _create_room(client)
    token = room["host_link"]["token"]

    async with factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(token))
            )
        ).scalar_one()
        link.expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
        await session.commit()

    resp = await client.get(f"/invites/{token}")
    assert resp.status_code == 200
    assert resp.json()["participant_id"] == room["host_participant_id"]
