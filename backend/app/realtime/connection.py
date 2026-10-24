"""Per-connection state shared by the realtime handlers.

The server-authenticated identity bound to a Socket.IO connection on ``join``,
the injectable session-factory type, and the uniform error reply.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ParticipantRole

# A zero-arg callable returning an async-session context manager. Defaults to the
# app session factory; tests inject one bound to an in-memory database.
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


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


async def load_identity(sio: Any, sid: str) -> JoinedIdentity | None:
    """Return the authenticated identity bound to ``sid`` on join, or ``None``."""
    session = await sio.get_session(sid)
    return session if isinstance(session, JoinedIdentity) else None


async def reject(sio: Any, sid: str, message: str) -> dict[str, Any]:
    """Emit an ``error`` to the caller only and return a failure ack (no broadcast)."""
    error: dict[str, Any] = {"error": message}
    await sio.emit("error", error, to=sid)
    return {"ok": False, **error}
