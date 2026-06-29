"""API tests for board tokens (place / list / move; bound to a character).

Runs against a fresh in-memory sqlite schema with get_session overridden, so no
Postgres is needed. Drives the real ASGI app via httpx.ASGITransport.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from app.db.session import get_session
from app.main import create_app
from app.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield an ASGI client wired to a fresh in-memory DB."""
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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await engine.dispose()


async def _make_room(client: httpx.AsyncClient) -> str:
    resp = await client.post("/rooms", json={"name": "Goblin Ambush"})
    assert resp.status_code == 201
    return str(resp.json()["room"]["id"])


async def _add_player(client: httpx.AsyncClient, room_id: str) -> str:
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Goblin", "max_hp": 7},
    )
    assert resp.status_code == 201
    return str(resp.json()["character_id"])


@pytest.mark.asyncio
async def test_place_token_bound_to_character(client: httpx.AsyncClient) -> None:
    """POST /rooms/{id}/tokens -> 201 with the token bound to the character + coords."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)

    resp = await client.post(
        f"/rooms/{room_id}/tokens",
        json={"character_id": character_id, "x": 3, "y": 5, "size": 2},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["room_id"] == room_id
    assert body["character_id"] == character_id
    assert (body["x"], body["y"], body["size"]) == (3, 5, 2)
    assert "id" in body


@pytest.mark.asyncio
async def test_place_token_defaults(client: httpx.AsyncClient) -> None:
    """Omitted coords/size default to origin (0,0) and size 1 (Medium)."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)

    resp = await client.post(f"/rooms/{room_id}/tokens", json={"character_id": character_id})

    assert resp.status_code == 201
    body = resp.json()
    assert (body["x"], body["y"], body["size"]) == (0, 0, 1)


@pytest.mark.asyncio
async def test_place_token_second_for_same_character_conflicts(
    client: httpx.AsyncClient,
) -> None:
    """A character has at most one token: placing a second one is a 409."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)

    first = await client.post(f"/rooms/{room_id}/tokens", json={"character_id": character_id})
    assert first.status_code == 201

    second = await client.post(f"/rooms/{room_id}/tokens", json={"character_id": character_id})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_place_token_unknown_room_404(client: httpx.AsyncClient) -> None:
    """Placing into a non-existent room is a 404."""
    resp = await client.post(
        f"/rooms/{uuid.uuid4()}/tokens",
        json={"character_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_place_token_unknown_character_404(client: httpx.AsyncClient) -> None:
    """A known room but unknown character is a 404."""
    room_id = await _make_room(client)
    resp = await client.post(
        f"/rooms/{room_id}/tokens",
        json={"character_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_place_token_foreign_character_422(client: httpx.AsyncClient) -> None:
    """A character from another room cannot be bound to this room's token (422)."""
    room_a = await _make_room(client)
    room_b = await _make_room(client)
    char_b = await _add_player(client, room_b)

    resp = await client.post(
        f"/rooms/{room_a}/tokens",
        json={"character_id": char_b},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_place_token_out_of_bounds_422(client: httpx.AsyncClient) -> None:
    """Negative coords and oversized footprints are rejected by the schema."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)

    neg = await client.post(
        f"/rooms/{room_id}/tokens",
        json={"character_id": character_id, "x": -1},
    )
    assert neg.status_code == 422

    big = await client.post(
        f"/rooms/{room_id}/tokens",
        json={"character_id": character_id, "size": 99},
    )
    assert big.status_code == 422


@pytest.mark.asyncio
async def test_list_tokens_reconnect_safe(client: httpx.AsyncClient) -> None:
    """GET /rooms/{id}/tokens returns every placed token (board hydrate on connect)."""
    room_id = await _make_room(client)
    char1 = await _add_player(client, room_id)
    char2 = await _add_player(client, room_id)

    await client.post(f"/rooms/{room_id}/tokens", json={"character_id": char1, "x": 1, "y": 1})
    await client.post(f"/rooms/{room_id}/tokens", json={"character_id": char2, "x": 2, "y": 2})

    resp = await client.get(f"/rooms/{room_id}/tokens")
    assert resp.status_code == 200
    tokens = resp.json()
    assert len(tokens) == 2
    assert {t["character_id"] for t in tokens} == {char1, char2}


@pytest.mark.asyncio
async def test_list_tokens_unknown_room_404(client: httpx.AsyncClient) -> None:
    """Listing tokens for a non-existent room is a 404."""
    resp = await client.get(f"/rooms/{uuid.uuid4()}/tokens")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_token_moves_and_resizes(client: httpx.AsyncClient) -> None:
    """PATCH updates only the supplied fields; others are unchanged."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)
    placed = await client.post(
        f"/rooms/{room_id}/tokens",
        json={"character_id": character_id, "x": 1, "y": 1, "size": 1},
    )
    token_id = placed.json()["id"]

    resp = await client.patch(
        f"/rooms/{room_id}/tokens/{token_id}",
        json={"x": 4, "size": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["x"], body["y"], body["size"]) == (4, 1, 3)


@pytest.mark.asyncio
async def test_update_token_empty_body_422(client: httpx.AsyncClient) -> None:
    """PATCH with no fields is rejected (422)."""
    room_id = await _make_room(client)
    character_id = await _add_player(client, room_id)
    placed = await client.post(f"/rooms/{room_id}/tokens", json={"character_id": character_id})
    token_id = placed.json()["id"]

    resp = await client.patch(f"/rooms/{room_id}/tokens/{token_id}", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_token_wrong_room_404(client: httpx.AsyncClient) -> None:
    """A token id that belongs to another room is not found via this room (404)."""
    room_a = await _make_room(client)
    room_b = await _make_room(client)
    char_a = await _add_player(client, room_a)
    placed = await client.post(f"/rooms/{room_a}/tokens", json={"character_id": char_a})
    token_id = placed.json()["id"]

    resp = await client.patch(f"/rooms/{room_b}/tokens/{token_id}", json={"x": 2})
    assert resp.status_code == 404
