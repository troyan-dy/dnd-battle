"""The authenticated ``join`` handshake of the realtime board transport.

On ``join`` the client presents its invite **token** (the credential it already
holds — same one ``GET /invites/{token}`` resolves); the server:

1. resolves the token to an identity via :func:`resolve_active_invite` — the SAME
   security rules as the HTTP resolve (unknown / revoked / expired -> uniform
   failure, no enumeration oracle). The ``roomId`` is taken from the *resolved
   link*, never from the client, so a visitor can only join the room their link
   binds them to.
2. places the client into the Socket.IO room ``room:{roomId}`` (plus its role
   sub-room);
3. pushes the FULL current :class:`BoardState` (every token + character) so the
   client can render immediately. This is a complete, idempotent read, so a client
   that reloads its link resyncs cleanly (reconnect-safe, CLAUDE.md rule 2).

The resolved identity is stashed in the per-connection Socket.IO session
(``save_session``) so a later ``action`` event can be attributed to an
authenticated actor without trusting the client.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.enums import ParticipantRole
from app.realtime.connection import JoinedIdentity, SessionFactory, reject
from app.realtime.rooms import role_room_name, room_name
from app.schemas.board import BoardState
from app.services.board import build_board_state
from app.services.invites import resolve_active_invite

# Rejection for a join that carries no usable token at all.
_TOKEN_REQUIRED_ERROR = "token is required to join a room."
# Uniform failure for a join whose token is not resolvable. Mirrors the HTTP
# resolver: never reveals whether a token never existed vs. was revoked/expired.
_INVALID_TOKEN_ERROR = "Invalid or expired invite link."


async def handle_join(
    sio: Any,
    sid: str,
    message: Any,
    *,
    session_factory: SessionFactory = async_session_factory,
) -> dict[str, Any]:
    """Authenticate a join via invite token, enter the room, and push BoardState.

    The return value is delivered to the client's ``emit`` acknowledgement
    callback. On any failure (missing or non-resolvable token) emit an ``error``
    event to the caller and return a failure ack without joining anything.
    """
    token = _extract_token(message)
    if token is None:
        return await reject(sio, sid, _TOKEN_REQUIRED_ERROR)

    async with session_factory() as session:
        joined = await _resolve_join(session, token)
    if joined is None:
        return await reject(sio, sid, _INVALID_TOKEN_ERROR)

    identity, board = joined
    await _enter_board(sio, sid, identity=identity, board=board)
    return _join_ack(identity)


def _extract_token(message: Any) -> str | None:
    """Pull a non-blank ``token`` string out of an arbitrary client payload."""
    if isinstance(message, dict):
        raw = message.get("token")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


async def _resolve_join(
    session: AsyncSession,
    token: str,
) -> tuple[JoinedIdentity, BoardState] | None:
    """Resolve ``token`` to its identity + that role's board, or ``None`` if invalid."""
    resolved = await resolve_active_invite(session, token)
    if resolved is None:
        return None
    # Fog of war: a player never receives the host's hidden tokens (CLAUDE.md
    # rule 3 — enforced on the server); the host receives the full board.
    is_host = resolved.role == ParticipantRole.host
    board = await build_board_state(session, resolved.room_id, include_hidden=is_host)
    identity = JoinedIdentity(
        room_id=resolved.room_id,
        role=resolved.role,
        participant_id=resolved.participant_id,
        character_id=resolved.character_id,
    )
    return identity, board


async def _enter_board(
    sio: Any,
    sid: str,
    *,
    identity: JoinedIdentity,
    board: BoardState,
) -> None:
    """Join the board's rooms, remember the identity and push the full snapshot."""
    room_id = str(identity.room_id)
    await sio.enter_room(sid, room_name(room_id))
    # Also join the role-specific sub-room so fog-of-war broadcasts can target hosts
    # (or players) only.
    await sio.enter_room(sid, role_room_name(room_id, identity.role))
    # Remember this connection's authenticated identity for later `action` events.
    await sio.save_session(sid, identity)
    # Push the full authoritative snapshot to just this client.
    await sio.emit("boardState", board.model_dump(mode="json"), to=sid)


def _join_ack(identity: JoinedIdentity) -> dict[str, Any]:
    """The success acknowledgement returned to the joining client."""
    character_id = None if identity.character_id is None else str(identity.character_id)
    return {
        "ok": True,
        "roomId": str(identity.room_id),
        "participantId": str(identity.participant_id),
        "role": identity.role.value,
        "characterId": character_id,
    }
