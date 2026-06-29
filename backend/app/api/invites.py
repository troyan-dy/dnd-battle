"""Invite-link resolution router.

Flow for ``GET /invites/{token}`` (no auth gate — the invite link *is* the
credential, see CLAUDE.md Phase 1):

1. Hash the presented plaintext token and match the unique ``token_hash`` column.
2. Reject anything that is unknown, revoked, or expired with a **uniform 404** so
   the endpoint is not an enumeration oracle (no way to tell "never existed" from
   "revoked" / "expired").
3. For a valid, active link, return ``{room_id, participant_id, role, character_id}``.

The actual resolution lives in :func:`app.services.invites.resolve_active_invite`
so this HTTP endpoint and the realtime Socket.IO ``join`` handshake authenticate a
token through exactly the same rules.

**Reconnect-safe (CLAUDE.md rule 2):** resolution is a pure, idempotent read — it
never mutates the link (in particular it does *not* set ``used_at``), so a client
that reloads its link can always re-resolve and resync.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.room import ResolveInviteResponse
from app.services.invites import resolve_active_invite

router = APIRouter(prefix="/invites", tags=["invites"])

# Uniform error for any non-resolvable link (unknown / revoked / expired). Using a
# single message + status avoids leaking which tokens ever existed.
_INVALID_LINK_DETAIL = "Invalid or expired invite link."


@router.get("/{token}", response_model=ResolveInviteResponse)
async def resolve_invite(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResolveInviteResponse:
    """Resolve an invite token to its (room, participant, role, character) binding."""
    resolved = await resolve_active_invite(session, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_INVALID_LINK_DETAIL,
        )

    return ResolveInviteResponse(
        room_id=resolved.room_id,
        participant_id=resolved.participant_id,
        role=resolved.role,
        character_id=resolved.character_id,
    )
