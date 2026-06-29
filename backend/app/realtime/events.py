"""Socket.IO event handlers for the realtime board transport.

Scope of this module (Phase 4, first task — "Socket.IO mounted; client connects"):
establish the connection lifecycle and a minimal room-join handshake so a client
can connect and be placed into the Socket.IO room that mirrors its D&D ``Room``
id. Sending the FULL current BoardState on join, the versioned Action protocol,
server-side intent validation and broadcasting are the *next* Phase 4 tasks and
are deliberately NOT implemented here.

Permissions note (CLAUDE.md rule 3): identity/permission binding via the invite
token is enforced when BoardState-on-join lands. This task is pure transport
plumbing, so ``connect``/``join`` accept without an auth check yet.

Handler bodies are kept as plain, fully-typed module functions and registered via
``sio.on(name, handler)`` (rather than decorators) so they stay unit-testable with
a fake server and so static typing is unaffected by the untyped Socket.IO library.
"""

from __future__ import annotations

from typing import Any

# Socket.IO rooms share a flat namespace per server; prefix the D&D Room id so
# board rooms can never collide with any other room name we introduce later.
ROOM_PREFIX = "room:"


def room_name(room_id: str) -> str:
    """Return the Socket.IO room name mirroring a given D&D ``Room`` id."""
    return f"{ROOM_PREFIX}{room_id}"


def _extract_room_id(data: Any) -> str | None:
    """Pull a non-blank ``roomId`` string out of an arbitrary client payload."""
    if isinstance(data, dict):
        raw = data.get("roomId")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


async def handle_connect(sio: Any, sid: str, environ: Any, auth: Any = None) -> bool:
    """Accept a new Socket.IO connection.

    Returning ``True`` accepts the connection. No identity/permission check yet
    (see module docstring); accepting here keeps this transport task isolated.
    """
    return True


async def handle_disconnect(sio: Any, sid: str) -> None:
    """Handle a client disconnect.

    Socket.IO automatically removes the ``sid`` from every room it had joined, so
    there is nothing to clean up until a live in-memory BoardState exists.
    """
    return None


async def handle_join(sio: Any, sid: str, data: Any) -> dict[str, Any]:
    """Place a connected client into the Socket.IO room for ``data['roomId']``.

    The return value is delivered to the client's ``emit`` acknowledgement
    callback. When ``roomId`` is missing or blank, emit an ``error`` event to the
    caller and return a failure ack instead of joining anything.
    """
    room_id = _extract_room_id(data)
    if room_id is None:
        error: dict[str, Any] = {"error": "roomId is required to join a room."}
        await sio.emit("error", error, to=sid)
        return {"ok": False, **error}

    await sio.enter_room(sid, room_name(room_id))
    # Notify just this client that the join succeeded. The full BoardState payload
    # is added by the next Phase 4 task; for now this is a lightweight handshake.
    await sio.emit("joined", {"roomId": room_id}, to=sid)
    return {"ok": True, "roomId": room_id}


def register_handlers(sio: Any) -> None:
    """Attach the connection-lifecycle and ``join`` handlers to a Socket.IO server.

    Handlers are bound as closures that forward to the testable module functions
    above, passing the ``sio`` server instance through explicitly.
    """

    async def _connect(sid: str, environ: Any, auth: Any = None) -> bool:
        return await handle_connect(sio, sid, environ, auth)

    async def _disconnect(sid: str) -> None:
        await handle_disconnect(sio, sid)

    async def _join(sid: str, data: Any) -> dict[str, Any]:
        return await handle_join(sio, sid, data)

    sio.on("connect", _connect)
    sio.on("disconnect", _disconnect)
    sio.on("join", _join)
