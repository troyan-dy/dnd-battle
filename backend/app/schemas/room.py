"""Pydantic request/response contracts for the room API.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
Invite-link plaintext appears in a response model exactly once — when the room
is created — and is never persisted (only its SHA-256 hash is, server-side).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ParticipantRole, RoomStatus

# D&D 2024 ability scores range 1..30 (PHB caps player scores at 20, but monsters
# and magic items can push to 30). 10 is the unmodified human average.
ABILITY_SCORE_MIN = 1
ABILITY_SCORE_MAX = 30
ABILITY_SCORE_DEFAULT = 10


class AbilityScores(BaseModel):
    """The six D&D 2024 ability scores. Each defaults to the average (10)."""

    strength: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    constitution: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    intelligence: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    wisdom: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)


class CreateRoomRequest(BaseModel):
    """Host's request to open a new encounter session."""

    name: str = Field(min_length=1, max_length=120, description="Encounter / room name.")
    host_display_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional friendly name shown for the DM.",
    )


class RoomSummary(BaseModel):
    """Public view of a freshly created room."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: RoomStatus


class InviteLinkResponse(BaseModel):
    """A shareable invite link. ``token`` is a secret returned only at creation."""

    token: str = Field(description="Plaintext invite token — shown once, never stored.")
    url: str = Field(description="Full shareable URL: {APP_BASE_URL}/join/{token}.")


class CreateRoomResponse(BaseModel):
    """Result of creating a room: the room, the host participant, and host link."""

    room: RoomSummary
    host_participant_id: uuid.UUID
    host_role: ParticipantRole
    host_link: InviteLinkResponse


class AddPlayerRequest(BaseModel):
    """Host's request to add a player participant + their character slot to a room."""

    character_name: str = Field(
        min_length=1,
        max_length=120,
        description="Name of the character slot the player will control.",
    )
    max_hp: int = Field(gt=0, le=1000, description="The character's maximum hit points.")
    ability_scores: AbilityScores = Field(
        default_factory=AbilityScores,
        description="The six D&D 2024 ability scores; each defaults to 10 if omitted.",
    )
    portrait_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional http(s) URL of a portrait image for the character.",
    )
    display_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional friendly name shown for the player.",
    )

    @field_validator("portrait_url")
    @classmethod
    def _validate_portrait_url(cls, value: str | None) -> str | None:
        """Normalize empty/blank to None; require an http(s) scheme when present."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
            raise ValueError("portrait_url must be an http:// or https:// URL.")
        return trimmed


class AddPlayerResponse(BaseModel):
    """Result of adding a player: the participant, their character, and invite link.

    The invite link is bound to (room, participant, character): opening it later
    resolves the player to exactly this character slot.
    """

    participant_id: uuid.UUID
    character_id: uuid.UUID
    role: ParticipantRole
    invite_link: InviteLinkResponse


class RevokeLinksResponse(BaseModel):
    """Result of revoking a participant's invite link(s).

    ``revoked`` is the number of *previously active* links that this call
    disabled. The endpoint is idempotent: a second call revokes ``0`` more,
    because already-revoked (or expired) links are left untouched.
    """

    revoked: int = Field(ge=0, description="How many active links this call revoked.")


class MapResponse(BaseModel):
    """Result of uploading (or describing) a room's current map image.

    ``url`` is the server path that streams the stored image back
    (``GET /rooms/{room_id}/map``); the bytes themselves are never inlined here.
    """

    room_id: uuid.UUID
    content_type: str = Field(description="Validated image MIME type of the stored map.")
    url: str = Field(description="Path that serves the map image: /rooms/{room_id}/map.")


class ResolveInviteResponse(BaseModel):
    """Result of resolving an invite token -> who/where the link binds the visitor.

    Returned by ``GET /invites/{token}`` for a valid, active link. ``character_id``
    is ``None`` for a host (the DM controls no single character slot).
    """

    room_id: uuid.UUID
    participant_id: uuid.UUID
    role: ParticipantRole
    character_id: uuid.UUID | None
