"""API tests for POST /rooms (create room -> room id + host link).

Runs against a fresh in-memory sqlite schema with get_session overridden, so no
Postgres is needed. Drives the real ASGI app via httpx.ASGITransport.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from app.db.session import get_session
from app.main import create_app
from app.models import Base, InviteLink, Participant, ParticipantRole, Room, RoomStatus
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


@pytest.mark.asyncio
async def test_create_room_returns_id_and_host_link(
    client_and_factory: ClientFactory,
) -> None:
    """POST /rooms -> 201 with room id, host participant, and a host invite link."""
    client, factory = client_and_factory

    resp = await client.post(
        "/rooms",
        json={"name": "Goblin Ambush", "host_display_name": "DM Bob"},
    )

    assert resp.status_code == 201
    body = resp.json()

    # Room summary
    assert body["room"]["name"] == "Goblin Ambush"
    assert body["room"]["status"] == RoomStatus.lobby.value
    room_id = body["room"]["id"]

    # Host participant
    assert body["host_role"] == ParticipantRole.host.value
    host_id = body["host_participant_id"]

    # Host link: plaintext token + shareable url
    token = body["host_link"]["token"]
    assert token
    assert body["host_link"]["url"].endswith("/join/" + token)

    # Persistence: exactly one room, one host participant, one invite link.
    async with factory() as session:
        rooms = (await session.execute(select(Room))).scalars().all()
        assert len(rooms) == 1
        assert str(rooms[0].id) == room_id

        host = (await session.execute(select(Participant))).scalars().one()
        assert str(host.id) == host_id
        assert host.role is ParticipantRole.host
        assert host.character_id is None

        invite = (await session.execute(select(InviteLink))).scalars().one()
        assert str(invite.participant_id) == host_id
        assert str(invite.room_id) == room_id
        # Security invariant: only the SHA-256 hash is stored, never the plaintext.
        assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert invite.token_hash != token


@pytest.mark.asyncio
async def test_create_room_mints_unique_tokens(
    client_and_factory: ClientFactory,
) -> None:
    """Two rooms get distinct, unguessable host tokens (no reuse)."""
    client, _ = client_and_factory

    first = (await client.post("/rooms", json={"name": "A"})).json()
    second = (await client.post("/rooms", json={"name": "B"})).json()

    assert first["host_link"]["token"] != second["host_link"]["token"]
    assert len(first["host_link"]["token"]) >= 32


@pytest.mark.asyncio
async def test_create_room_rejects_blank_name(
    client_and_factory: ClientFactory,
) -> None:
    """An empty room name fails validation with 422."""
    client, _ = client_and_factory
    resp = await client.post("/rooms", json={"name": ""})
    assert resp.status_code == 422
