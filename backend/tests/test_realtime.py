"""Tests for the Socket.IO realtime transport (mount + connect handshake).

Two layers:
- Unit tests drive the handler functions with a fake AsyncServer (AsyncMock) so the
  room-join logic is verified without a network or event loop server.
- An integration test drives the combined ASGI app via httpx to prove the REST API
  still works (FastAPI passthrough) AND the Socket.IO handshake is served, i.e. the
  server is genuinely mounted on FastAPI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import socketio
from app.main import create_app
from app.realtime import create_asgi_app, create_sio_server
from app.realtime.events import (
    ROOM_PREFIX,
    handle_connect,
    handle_disconnect,
    handle_join,
    register_handlers,
    room_name,
)


def _fake_sio() -> MagicMock:
    """A stand-in Socket.IO server with awaitable enter_room/emit spies."""
    sio = MagicMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    return sio


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


async def test_handle_join_enters_room_and_acks() -> None:
    sio = _fake_sio()

    ack = await handle_join(sio, "sid1", {"roomId": "room-42"})

    assert ack == {"ok": True, "roomId": "room-42"}
    sio.enter_room.assert_awaited_once_with("sid1", room_name("room-42"))
    sio.emit.assert_awaited_once_with("joined", {"roomId": "room-42"}, to="sid1")


async def test_handle_join_trims_room_id() -> None:
    sio = _fake_sio()

    ack = await handle_join(sio, "sid1", {"roomId": "  room-7  "})

    assert ack == {"ok": True, "roomId": "room-7"}
    sio.enter_room.assert_awaited_once_with("sid1", room_name("room-7"))


@pytest.mark.parametrize("data", [{}, {"roomId": ""}, {"roomId": "   "}, {"roomId": 5}, None, "x"])
async def test_handle_join_rejects_missing_room_id(data: object) -> None:
    sio = _fake_sio()

    ack = await handle_join(sio, "sid1", data)

    assert ack["ok"] is False
    assert "error" in ack
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_awaited_once()
    # The single emit is the error event addressed back to the caller.
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


def test_register_handlers_binds_events() -> None:
    sio = create_sio_server()
    # The default namespace should now have connect/disconnect/join handlers.
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
    # Engine.IO open packet ("0") carrying the session handshake JSON.
    assert response.text.startswith("0")
    assert "sid" in response.text
