"""Invite-link resolution router.

Flow for ``GET /invites/{token}`` (no auth gate — the invite link *is* the
credential, see CLAUDE.md Phase 1):

1. Hash the presented plaintext token and match the unique ``token_hash`` column.
2. Reject anything that is unknown, revoked, or expired with a **uniform 404** so
   the endpoint is not an enumeration oracle (no way to tell "never existed" from
   "revoked" / "expired").
3. For a valid, active link, return ``{room_id, participant_id, role, character_id}``.

**Reconnect-safe (CLAUDE.md rule 2):** resolution is a pure, idempotent read — it
never mutates the link (in particular it does *not* set ``used_at``), so a client
that reloads its link can always re-resolve and resync. One-time consumption
semantics belong to the separate "Link security" task.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.invite_link import InviteLink
from app.models.participant import Participant
from app.schemas.room import ResolveInviteResponse
from app.security.tokens import hash_token

router = APIRouter(prefix="/invites", tags=["invites"])

# Uniform error for any non-resolvable link (unknown / revoked / expired). Using a
# single message + status avoids leaking which tokens ever existed.
_INVALID_LINK_DETAIL = "Invalid or expired invite link."


def _is_active(link: InviteLink, now: dt.datetime) -> bool:
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


@router.get("/{token}", response_model=ResolveInviteResponse)
async def resolve_invite(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResolveInviteResponse:
    """Resolve an invite token to its (room, participant, role, character) binding."""
    link = (
        await session.execute(select(InviteLink).where(InviteLink.token_hash == hash_token(token)))
    ).scalar_one_or_none()

    if link is None or not _is_active(link, dt.datetime.now(dt.UTC)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_INVALID_LINK_DETAIL,
        )

    participant = await session.get(Participant, link.participant_id)
    if participant is None:  # pragma: no cover - FK guarantees presence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_INVALID_LINK_DETAIL,
        )

    return ResolveInviteResponse(
        room_id=link.room_id,
        participant_id=participant.id,
        role=participant.role,
        character_id=participant.character_id,
    )
