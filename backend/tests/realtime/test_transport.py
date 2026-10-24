"""Realtime transport unit tests: room naming, lifecycle, registration + mounting.

Unit tests drive the handler functions with a fake AsyncServer (AsyncMock) so the
connection lifecycle + join failure paths are verified without a network. An
integration test drives the combined ASGI app via httpx to prove the REST API still
works (FastAPI passthrough) AND the Socket.IO handshake is served, i.e. the server
is genuinely mounted on FastAPI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import socketio
from app.main import create_app
from app.realtime import create_asgi_app, create_sio_server
from app.realtime.events import handle_connect, handle_disconnect, register_handlers
from app.realtime.join import handle_join
from app.realtime.rooms import ROOM_PREFIX, room_name
from app.realtime.sequence import RoomSequencer

from tests.realtime.support import (
    fake_sio,
)

# --- transport unit tests -------------------------------------------------------


def test_room_name_is_prefixed() -> None:
    assert room_name("abc-123") == f"{ROOM_PREFIX}abc-123"


async def test_handle_connect_accepts() -> None:
    sio = fake_sio()
    assert await handle_connect(sio, "sid1", {}, None) is True


async def test_handle_disconnect_is_noop() -> None:
    sio = fake_sio()
    await handle_disconnect(sio, "sid1")
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_not_awaited()


@pytest.mark.parametrize(
    "message",
    [{}, {"token": ""}, {"token": "   "}, {"token": 5}, None, "x"],
)
async def test_handle_join_rejects_missing_token(message: object) -> None:
    """A join with no usable token errors back to the caller and never enters a room."""
    sio = fake_sio()

    ack = await handle_join(sio, "sid1", message)

    assert ack["ok"] is False
    assert "error" in ack
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


def test_room_sequencer_is_monotonic_and_per_room() -> None:
    sequencer = RoomSequencer()
    assert sequencer.next_seq("a") == 0
    assert sequencer.next_seq("a") == 1
    assert sequencer.next_seq("b") == 0  # independent per room
    assert sequencer.next_seq("a") == 2


def test_room_sequencer_seed_recovers_after_restart() -> None:
    """seed sets a fresh room's counter and never moves it backwards (idempotent)."""
    sequencer = RoomSequencer()
    # A freshly started process recovers the durable high-water for a room it has
    # never seen, then continues from there rather than colliding from 0.
    sequencer.seed("a", 5)
    assert sequencer.next_seq("a") == 5
    assert sequencer.next_seq("a") == 6
    # Seeding with a stale/lower value is ignored (never rewinds the counter).
    sequencer.seed("a", 3)
    assert sequencer.next_seq("a") == 7
    # Seeding ahead of the in-memory counter advances it.
    sequencer.seed("a", 20)
    assert sequencer.next_seq("a") == 20


# --- registration + mounting ----------------------------------------------------


def test_register_handlers_binds_events() -> None:
    sio = create_sio_server()
    handlers = sio.handlers["/"]
    assert {"connect", "disconnect", "join", "action"} <= set(handlers)


def test_create_sio_server_returns_async_server() -> None:
    sio = create_sio_server()
    assert isinstance(sio, socketio.AsyncServer)


def test_register_handlers_is_callable_on_plain_mock() -> None:
    sio = MagicMock()
    register_handlers(sio)
    registered = {call.args[0] for call in sio.on.call_args_list}
    assert {"connect", "disconnect", "join", "action"} == registered


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
