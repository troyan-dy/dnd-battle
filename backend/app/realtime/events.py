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

On a successful join the resolved identity is stashed in the per-connection
Socket.IO session (``save_session``) so a later ``action`` event can be attributed
to an authenticated actor without trusting the client. The ``action`` handler then
parses the client's :class:`ActionIntent`, validates it against state +
permissions (:func:`validate_intent`), applies the durable effect
(:func:`apply_action`), stamps a server :class:`Action` (id + monotonic per-room
``seq``) and broadcasts it to everyone in ``room:{roomId}``. A malformed or
unauthorised intent is rejected to the caller and NEVER broadcast.

Handler bodies are kept as plain, fully-typed module functions and registered via
``sio.on(name, handler)`` (rather than decorators) so they stay unit-testable with
a fake server and so static typing is unaffected by the untyped Socket.IO library.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.enums import ParticipantRole
from app.realtime.sequence import RoomSequencer
from app.schemas.action import (
    Action,
    ActionIntent,
    AttackIntentPayload,
    BroadcastActionPayload,
)
from app.services.actions import (
    IntentValidationError,
    apply_action,
    resolve_attack,
    validate_intent,
)
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

# Rejection shown when an `action` arrives on a connection that never joined a room.
_NOT_JOINED_ERROR = "Join a room before sending actions."
# Rejection for an intent that fails to parse (bad protocol version / bounds / type).
_MALFORMED_ACTION_ERROR = "Malformed or unsupported action."

# Process RNG used for server-authoritative dice rolls (CLAUDE.md rule 1). Tests
# inject a seeded Random for deterministic results.
_DEFAULT_RNG = random.Random()


@dataclass(frozen=True)
class JoinedIdentity:
    """The server-authenticated identity bound to a connection after a join.

    Stashed in the Socket.IO per-connection session so subsequent ``action`` events
    are attributed to this actor — derived from the resolved invite, never the
    client payload (CLAUDE.md rule 1).
    """

    room_id: uuid.UUID
    role: ParticipantRole
    participant_id: uuid.UUID
    character_id: uuid.UUID | None


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
    # Remember this connection's authenticated identity for later `action` events.
    await sio.save_session(
        sid,
        JoinedIdentity(
            room_id=resolved.room_id,
            role=resolved.role,
            participant_id=resolved.participant_id,
            character_id=resolved.character_id,
        ),
    )
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


async def _load_identity(sio: Any, sid: str) -> JoinedIdentity | None:
    """Return the authenticated identity bound to ``sid`` on join, or ``None``."""
    session = await sio.get_session(sid)
    return session if isinstance(session, JoinedIdentity) else None


async def handle_action(
    sio: Any,
    sid: str,
    data: Any,
    *,
    sequencer: RoomSequencer,
    rng: random.Random = _DEFAULT_RNG,
    session_factory: SessionFactory = async_session_factory,
) -> dict[str, Any]:
    """Validate a client's action intent, apply it, and broadcast the Action.

    The actor's identity (room / role / character) comes from the join-time
    session, never the client payload. The pipeline is: parse the
    :class:`ActionIntent` (rejecting bad version / bounds / unknown type) ->
    :func:`validate_intent` (permissions + state) -> :func:`apply_action` (durable
    effect) -> stamp a server :class:`Action` with a per-room monotonic ``seq`` ->
    broadcast ``action`` to everyone in the room. Any parse or validation failure
    is acked back to the caller and is NEVER broadcast.
    """
    identity = await _load_identity(sio, sid)
    if identity is None:
        return await _reject_action(sio, sid, _NOT_JOINED_ERROR)

    try:
        intent = ActionIntent.model_validate(data)
    except ValidationError:
        return await _reject_action(sio, sid, _MALFORMED_ACTION_ERROR)

    async with session_factory() as session:
        try:
            payload = await validate_intent(
                session,
                room_id=identity.room_id,
                role=identity.role,
                character_id=identity.character_id,
                intent=intent,
            )
        except IntentValidationError as exc:
            return await _reject_action(sio, sid, exc.reason)

        # An attack is RESOLVED server-side (dice rolled here, damage applied) and
        # broadcast as its result payload; every other action's durable effect is
        # applied and the validated intent payload is broadcast unchanged.
        broadcast_payload: BroadcastActionPayload
        if isinstance(payload, AttackIntentPayload):
            broadcast_payload = await resolve_attack(
                session, room_id=identity.room_id, payload=payload, rng=rng
            )
        else:
            await apply_action(session, room_id=identity.room_id, payload=payload)
            broadcast_payload = payload
        await session.commit()

    seq = sequencer.next_seq(str(identity.room_id))
    action = Action(
        id=uuid.uuid4(),
        room_id=identity.room_id,
        actor_participant_id=identity.participant_id,
        seq=seq,
        payload=broadcast_payload,
    )
    # Broadcast to EVERYONE in the room (including the sender, which reconciles its
    # optimistic update against this authoritative event — next Phase 4 task).
    await sio.emit("action", action.model_dump(mode="json"), room=room_name(str(identity.room_id)))
    return {"ok": True, "actionId": str(action.id), "seq": seq}


async def _reject_action(sio: Any, sid: str, message: str) -> dict[str, Any]:
    """Emit an action ``error`` to the caller and return a failure ack (no broadcast)."""
    error: dict[str, Any] = {"error": message}
    await sio.emit("error", error, to=sid)
    return {"ok": False, **error}


def register_handlers(sio: Any) -> None:
    """Attach the connection-lifecycle and ``join`` handlers to a Socket.IO server.

    Handlers are bound as closures that forward to the testable module functions
    above, passing the ``sio`` server instance through explicitly. A single
    :class:`RoomSequencer` is created here and shared so every broadcast Action gets
    a per-room monotonic ``seq`` for this server process.
    """
    sequencer = RoomSequencer()
    rng = random.Random()

    async def _connect(sid: str, environ: Any, auth: Any = None) -> bool:
        return await handle_connect(sio, sid, environ, auth)

    async def _disconnect(sid: str) -> None:
        await handle_disconnect(sio, sid)

    async def _join(sid: str, data: Any) -> dict[str, Any]:
        return await handle_join(sio, sid, data)

    async def _action(sid: str, data: Any) -> dict[str, Any]:
        return await handle_action(sio, sid, data, sequencer=sequencer, rng=rng)

    sio.on("connect", _connect)
    sio.on("disconnect", _disconnect)
    sio.on("join", _join)
    sio.on("action", _action)
