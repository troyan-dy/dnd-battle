"""Socket.IO event handlers for the realtime board transport.

This module owns the connection lifecycle and the authenticated ``join``
handshake. On ``join`` the client presents its invite **token** (the credential it
already holds — same one ``GET /invites/{token}`` resolves); the server:

1. resolves the token to an identity via :func:`resolve_active_invite` — the SAME
   security rules as the HTTP resolve (unknown / revoked / expired -> uniform
   failure, no enumeration oracle). The ``roomId`` is taken from the *resolved
   link*, never from the client, so a visitor can only join the room their link
   binds them to.
2. places the client into the Socket.IO room ``room:{roomId}``;
3. pushes the FULL current :class:`BoardState` (every token + character) so the
   client can render immediately. This is a complete, idempotent read, so a client
   that reloads its link resyncs cleanly (reconnect-safe, CLAUDE.md rule 2).

The versioned Action protocol, server-side intent validation and broadcasting are
later Phase 4 tasks and are intentionally not implemented here.

Handler bodies are kept as plain, fully-typed module functions and registered via
``sio.on(name, handler)`` (rather than decorators) so they stay unit-testable with
a fake server and so static typing is unaffected by the untyped Socket.IO library.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.services.board import build_board_state
from app.services.invites import resolve_active_invite

# Socket.IO rooms share a flat namespace per server; prefix the D&D Room id so
# board rooms can never collide with any other room name we introduce later.
ROOM_PREFIX = "room:"

# A zero-arg callable returning an async-session context manager. Defaults to the
# app session factory; tests inject one bound to an in-memory database.
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Uniform failure for a join whose token is missing or not resolvable. Mirrors the
# HTTP resolver: never reveals whether a token never existed vs. was revoked/expired.
_INVALID_TOKEN_ERROR = "Invalid or expired invite link."


def room_name(room_id: str) -> str:
    """Return the Socket.IO room name mirroring a given D&D ``Room`` id."""
    return f"{ROOM_PREFIX}{room_id}"


def _extract_token(data: Any) -> str | None:
    """Pull a non-blank ``token`` string out of an arbitrary client payload."""
    if isinstance(data, dict):
        raw = data.get("token")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


async def handle_connect(sio: Any, sid: str, environ: Any, auth: Any = None) -> bool:
    """Accept a new Socket.IO connection.

    Returning ``True`` accepts the connection. Identity is bound on ``join`` (which
    carries the invite token), so the bare connection accepts without an auth check.
    """
    return True


async def handle_disconnect(sio: Any, sid: str) -> None:
    """Handle a client disconnect.

    Socket.IO automatically removes the ``sid`` from every room it had joined, so
    there is nothing to clean up until a live in-memory BoardState exists.
    """
    return None


async def handle_join(
    sio: Any,
    sid: str,
    data: Any,
    *,
    session_factory: SessionFactory = async_session_factory,
) -> dict[str, Any]:
    """Authenticate a join via invite token, enter the room, and push BoardState.

    The return value is delivered to the client's ``emit`` acknowledgement
    callback. On any failure (missing or non-resolvable token) emit an ``error``
    event to the caller and return a failure ack without joining anything.
    """
    token = _extract_token(data)
    if token is None:
        return await _reject_join(sio, sid, "token is required to join a room.")

    async with session_factory() as session:
        resolved = await resolve_active_invite(session, token)
        if resolved is None:
            return await _reject_join(sio, sid, _INVALID_TOKEN_ERROR)
        board = await build_board_state(session, resolved.room_id)

    room_id = str(resolved.room_id)
    await sio.enter_room(sid, room_name(room_id))
    # Push the full authoritative snapshot to just this client.
    await sio.emit("boardState", board.model_dump(mode="json"), to=sid)

    character_id = str(resolved.character_id) if resolved.character_id is not None else None
    return {
        "ok": True,
        "roomId": room_id,
        "participantId": str(resolved.participant_id),
        "role": resolved.role.value,
        "characterId": character_id,
    }


async def _reject_join(sio: Any, sid: str, message: str) -> dict[str, Any]:
    """Emit a join ``error`` to the caller and return a failure ack."""
    error: dict[str, Any] = {"error": message}
    await sio.emit("error", error, to=sid)
    return {"ok": False, **error}


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
