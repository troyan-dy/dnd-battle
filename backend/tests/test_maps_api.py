"""API tests for room map upload + serve.

Runs against a fresh in-memory sqlite schema with get_session overridden and a
per-test temporary MAP_STORAGE_DIR (monkeypatched on app.config), so nothing
touches Postgres or the real filesystem. Drives the ASGI app via httpx.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from app import config
from app.db.session import get_session
from app.main import create_app
from app.models import Base, Room
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

ClientFactory = tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]

# A 1x1 transparent PNG (smallest valid-ish payload for upload tests).
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest_asyncio.fixture
async def client_and_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[ClientFactory]:
    """Yield an ASGI client on a fresh in-memory DB with a temp map storage dir."""
    monkeypatch.setattr(config, "MAP_STORAGE_DIR", str(tmp_path / "maps"))

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


async def _create_room(client: httpx.AsyncClient, name: str = "Room") -> str:
    resp = await client.post("/rooms", json={"name": name})
    assert resp.status_code == 201
    room_id: str = resp.json()["room"]["id"]
    return room_id


@pytest.mark.asyncio
async def test_upload_then_serve_map(client_and_factory: ClientFactory) -> None:
    """Host uploads a PNG; it is stored, the room points at it, and GET serves it."""
    client, factory = client_and_factory
    room_id = await _create_room(client)

    resp = await client.post(
        f"/rooms/{room_id}/map",
        files={"file": ("battlemap.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["room_id"] == room_id
    assert body["content_type"] == "image/png"
    assert body["url"] == f"/rooms/{room_id}/map"

    # Persistence: room carries the server-generated filename + content type.
    async with factory() as session:
        room = (
            (await session.execute(select(Room).where(Room.id == uuid.UUID(room_id))))
            .scalars()
            .one()
        )
        assert room.map_image_path is not None
        # Server-generated name, NOT the client filename (no traversal surface).
        assert room.map_image_path != "battlemap.png"
        assert room.map_image_path.endswith(".png")
        assert room.map_content_type == "image/png"
        stored = Path(config.MAP_STORAGE_DIR) / room.map_image_path
        assert stored.is_file()
        assert stored.read_bytes() == PNG_BYTES

    # Serving returns the exact bytes with the stored content type.
    served = await client.get(f"/rooms/{room_id}/map")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == PNG_BYTES


@pytest.mark.asyncio
async def test_upload_rejects_non_image(client_and_factory: ClientFactory) -> None:
    """A non-allowlisted content type is rejected with 415 and nothing is stored."""
    client, factory = client_and_factory
    room_id = await _create_room(client)

    resp = await client.post(
        f"/rooms/{room_id}/map",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415

    async with factory() as session:
        room = (
            (await session.execute(select(Room).where(Room.id == uuid.UUID(room_id))))
            .scalars()
            .one()
        )
        assert room.map_image_path is None


@pytest.mark.asyncio
async def test_upload_rejects_oversized(client_and_factory: ClientFactory) -> None:
    """An upload above the configured size cap is rejected with 413."""
    client, _ = client_and_factory
    room_id = await _create_room(client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MAX_MAP_UPLOAD_BYTES", 8)
        resp = await client.post(
            f"/rooms/{room_id}/map",
            files={"file": ("big.png", PNG_BYTES, "image/png")},
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_unknown_room_404(client_and_factory: ClientFactory) -> None:
    """Uploading to a nonexistent room fails with 404."""
    client, _ = client_and_factory
    missing = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"/rooms/{missing}/map",
        files={"file": ("m.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_map_when_none_404(client_and_factory: ClientFactory) -> None:
    """A room with no uploaded map serves 404."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    resp = await client.get(f"/rooms/{room_id}/map")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reupload_replaces_pointer(client_and_factory: ClientFactory) -> None:
    """Re-uploading swaps the room's map pointer to the new file."""
    client, factory = client_and_factory
    room_id = await _create_room(client)

    first = await client.post(
        f"/rooms/{room_id}/map",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
    )
    assert first.status_code == 201
    async with factory() as session:
        room = (
            (await session.execute(select(Room).where(Room.id == uuid.UUID(room_id))))
            .scalars()
            .one()
        )
        first_name = room.map_image_path

    second = await client.post(
        f"/rooms/{room_id}/map",
        files={"file": ("b.gif", PNG_BYTES, "image/gif")},
    )
    assert second.status_code == 201
    async with factory() as session:
        room = (
            (await session.execute(select(Room).where(Room.id == uuid.UUID(room_id))))
            .scalars()
            .one()
        )
        assert room.map_image_path != first_name
        assert room.map_image_path is not None
        assert room.map_image_path.endswith(".gif")
        assert room.map_content_type == "image/gif"
