"""Shared invite-link resolution (used by the HTTP router AND the realtime join).

Resolving a presented plaintext token to its (room, participant, role, character)
binding is security-sensitive and must behave identically everywhere a client
authenticates. Centralising it here guarantees the Socket.IO ``join`` handshake
enforces exactly the same rules as ``GET /invites/{token}``:

* hash the presented token and match the unique ``token_hash`` column;
* treat unknown / revoked / expired links uniformly as "not resolvable" (no
  enumeration oracle — callers surface a single generic failure);
* never mutate the link (no ``used_at`` write) so reloads can always re-resolve
  (reconnect-safe, CLAUDE.md rule 2).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ParticipantRole
from app.models.invite_link import InviteLink
from app.models.participant import Participant
from app.security.tokens import hash_token


@dataclass(frozen=True, slots=True)
class ResolvedInvite:
    """The identity an active invite token binds a visitor to."""

    room_id: uuid.UUID
    participant_id: uuid.UUID
    role: ParticipantRole
    character_id: uuid.UUID | None


def is_invite_active(link: InviteLink, now: dt.datetime) -> bool:
    """Return True iff the link is neither revoked nor past its expiry.

    Active == ``revoked_at IS NULL AND (expires_at IS NULL OR now < expires_at)``.
    ``expires_at`` may come back tz-naive from some backends (e.g. sqlite); treat
    such values as UTC so the comparison is always well defined.
    """
    if link.revoked_at is not None:
        return False
    expires_at = link.expires_at
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    return now < expires_at


async def resolve_active_invite(
    session: AsyncSession,
    token: str,
    *,
    now: dt.datetime | None = None,
) -> ResolvedInvite | None:
    """Resolve a plaintext token to its binding, or ``None`` if not resolvable.

    Returns ``None`` for an unknown, revoked, or expired link (callers map this to
    a single uniform failure). A pure read — never mutates the link.
    """
    if not token:
        return None
    moment = now if now is not None else dt.datetime.now(dt.UTC)

    link = (
        await session.execute(select(InviteLink).where(InviteLink.token_hash == hash_token(token)))
    ).scalar_one_or_none()
    if link is None or not is_invite_active(link, moment):
        return None

    participant = await session.get(Participant, link.participant_id)
    if participant is None:  # pragma: no cover - FK guarantees presence
        return None

    return ResolvedInvite(
        room_id=link.room_id,
        participant_id=participant.id,
        role=participant.role,
        character_id=participant.character_id,
    )
