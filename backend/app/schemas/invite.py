"""Pydantic contracts for invite links: minting, revoking and resolving them.

A plaintext invite token appears in :class:`InviteLinkResponse` exactly once (at
creation); only its SHA-256 hash is ever persisted, server-side.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models.enums import ParticipantRole


class InviteLinkResponse(BaseModel):
    """A shareable invite link. ``token`` is a secret returned only at creation."""

    token: str = Field(description="Plaintext invite token — shown once, never stored.")
    url: str = Field(description="Full shareable URL: {APP_BASE_URL}/join/{token}.")


class RevokeLinksResponse(BaseModel):
    """Result of revoking a participant's invite link(s).

    ``revoked`` is the number of *previously active* links that this call
    disabled. The endpoint is idempotent: a second call revokes ``0`` more,
    because already-revoked (or expired) links are left untouched.
    """

    revoked: int = Field(ge=0, description="How many active links this call revoked.")


class ResolveInviteResponse(BaseModel):
    """Result of resolving an invite token -> who/where the link binds the visitor.

    Returned by ``GET /invites/{token}`` for a valid, active link. ``character_id``
    is ``None`` for a host (the DM controls no single character slot).
    """

    room_id: uuid.UUID
    participant_id: uuid.UUID
    role: ParticipantRole
    character_id: uuid.UUID | None
