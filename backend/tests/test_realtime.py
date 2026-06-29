"""Tests for the Socket.IO realtime transport (mount + authenticated join).

Three layers:
- Unit tests drive the handler functions with a fake AsyncServer (AsyncMock) so the
  connection lifecycle + join failure paths are verified without a network.
- DB-backed join tests inject a session_factory bound to an in-memory sqlite schema
  so the token-authenticated join + FULL BoardState push is exercised end to end.
- An integration test drives the combined ASGI app via httpx to prove the REST API
  still works (FastAPI passthrough) AND the Socket.IO handshake is served, i.e. the
  server is genuinely mounted on FastAPI.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
import socketio
from app.main import create_app
from app.models import (
    Base,
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.realtime import create_asgi_app, create_sio_server
from app.realtime.events import (
    ROOM_PREFIX,
    handle_connect,
    handle_disconnect,
    handle_join,
    register_handlers,
    room_name,
)
from app.security.tokens import generate_token, hash_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def _fake_sio() -> MagicMock:
    """A stand-in Socket.IO server with awaitable enter_room/emit spies."""
    sio = MagicMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    return sio


# --- seeded in-memory DB --------------------------------------------------------


class SeededBoard:
    """Handles to a seeded room: tokens to render + the participants' invite tokens."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        room_id: uuid.UUID,
        host_token: str,
        player_token: str,
        player_participant_id: uuid.UUID,
        player_character_id: uuid.UUID,
    ) -> None:
        self.factory = factory
        self.room_id = room_id
        self.host_token = host_token
        self.player_token = player_token
        self.player_participant_id = player_participant_id
        self.player_character_id = player_character_id


@pytest_asyncio.fixture
async def seeded() -> AsyncIterator[SeededBoard]:
    """A room with a host link, a player (character + token), and a player link."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    host_token = generate_token()
    player_token = generate_token()

    async with factory() as session:
        room = Room(name="Goblin Ambush")
        session.add(room)
        await session.flush()

        character = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=20)
        session.add(character)
        await session.flush()

        host = Participant(room_id=room.id, role=ParticipantRole.host, display_name="DM")
        player = Participant(
            room_id=room.id,
            role=ParticipantRole.player,
            display_name="P1",
            character_id=character.id,
        )
        session.add_all([host, player])
        await session.flush()

        session.add_all(
            [
                InviteLink(
                    room_id=room.id, participant_id=host.id, token_hash=hash_token(host_token)
                ),
                InviteLink(
                    room_id=room.id,
                    participant_id=player.id,
                    token_hash=hash_token(player_token),
                ),
                Token(room_id=room.id, character_id=character.id, x=3, y=4, size=1),
            ]
        )
        await session.commit()

        board = SeededBoard(
            factory=factory,
            room_id=room.id,
            host_token=host_token,
            player_token=player_token,
            player_participant_id=player.id,
            player_character_id=character.id,
        )

    yield board
    await engine.dispose()


# --- transport unit tests -------------------------------------------------------


def test_room_name_is_prefixed() -> None:
    assert room_name("abc-123") == f"{ROOM_PREFIX}abc-123"


async def test_handle_connect_accepts() -> None:
    sio = _fake_sio()
    assert await handle_connect(sio, "sid1", {}, None) is True


async def test_handle_disconnect_is_noop() -> None:
    sio = _fake_sio()
    await handle_disconnect(sio, "sid1")
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_not_awaited()


@pytest.mark.parametrize("data", [{}, {"token": ""}, {"token": "   "}, {"token": 5}, None, "x"])
async def test_handle_join_rejects_missing_token(data: object) -> None:
    """A join with no usable token errors back to the caller and never enters a room."""
    sio = _fake_sio()

    ack = await handle_join(sio, "sid1", data)

    assert ack["ok"] is False
    assert "error" in ack
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


# --- DB-backed join tests -------------------------------------------------------


async def test_handle_join_player_enters_room_and_pushes_board_state(
    seeded: SeededBoard,
) -> None:
    """A valid player token joins the resolved room and receives the FULL BoardState."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["roomId"] == str(seeded.room_id)
    assert ack["participantId"] == str(seeded.player_participant_id)
    assert ack["role"] == ParticipantRole.player.value
    assert ack["characterId"] == str(seeded.player_character_id)

    # Entered the room derived from the link (never client-supplied).
    sio.enter_room.assert_awaited_once_with("sid1", room_name(str(seeded.room_id)))

    # The full snapshot was pushed to just this client.
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "boardState"
    assert kwargs == {"to": "sid1"}
    payload = args[1]
    assert payload["room_id"] == str(seeded.room_id)
    assert len(payload["tokens"]) == 1
    assert payload["tokens"][0]["x"] == 3
    assert payload["tokens"][0]["y"] == 4
    assert len(payload["characters"]) == 1
    assert payload["characters"][0]["name"] == "Aria"


async def test_handle_join_host_token_has_no_character(seeded: SeededBoard) -> None:
    """A host token joins the same room with role=host and characterId None."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.host_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["role"] == ParticipantRole.host.value
    assert ack["characterId"] is None
    sio.enter_room.assert_awaited_once_with("sid1", room_name(str(seeded.room_id)))


async def test_handle_join_trims_token(seeded: SeededBoard) -> None:
    """Surrounding whitespace on the token is trimmed before resolution."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": f"  {seeded.player_token}  "}, session_factory=seeded.factory
    )

    assert ack["ok"] is True


async def test_handle_join_unknown_token_is_rejected(seeded: SeededBoard) -> None:
    """An unknown token gets the uniform failure and never enters a room."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": "not-a-real-token"}, session_factory=seeded.factory
    )

    assert ack["ok"] is False
    assert ack["error"] == "Invalid or expired invite link."
    sio.enter_room.assert_not_awaited()
    args, _ = sio.emit.await_args
    assert args[0] == "error"


async def test_handle_join_revoked_token_is_rejected(seeded: SeededBoard) -> None:
    """A revoked link cannot join and gets the same uniform failure (no oracle)."""
    async with seeded.factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(seeded.player_token))
            )
        ).scalar_one()
        link.revoked_at = dt.datetime.now(dt.UTC)
        await session.commit()

    sio = _fake_sio()
    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is False
    assert ack["error"] == "Invalid or expired invite link."
    sio.enter_room.assert_not_awaited()


# --- registration + mounting ----------------------------------------------------


def test_register_handlers_binds_events() -> None:
    sio = create_sio_server()
    handlers = sio.handlers["/"]
    assert {"connect", "disconnect", "join"} <= set(handlers)


def test_create_sio_server_returns_async_server() -> None:
    sio = create_sio_server()
    assert isinstance(sio, socketio.AsyncServer)


def test_register_handlers_is_callable_on_plain_mock() -> None:
    sio = MagicMock()
    register_handlers(sio)
    registered = {call.args[0] for call in sio.on.call_args_list}
    assert {"connect", "disconnect", "join"} == registered


async def test_combined_asgi_app_serves_fastapi_health() -> None:
    """The wrapped ASGI app forwards non-socket.io requests to FastAPI."""
    app = create_asgi_app(create_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_combined_asgi_app_serves_socketio_handshake() -> None:
    """The wrapped ASGI app answers the Engine.IO handshake under /socket.io/."""
    app = create_asgi_app(create_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/socket.io/?EIO=4&transport=polling")

    assert response.status_code == 200
    assert response.text.startswith("0")
    assert "sid" in response.text
