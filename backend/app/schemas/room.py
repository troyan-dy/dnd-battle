"""Pydantic request/response contracts for the room API.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
Invite-link plaintext appears in a response model exactly once — when the room
is created — and is never persisted (only its SHA-256 hash is, server-side).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ParticipantRole, RoomStatus


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
    display_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional friendly name shown for the player.",
    )


class AddPlayerResponse(BaseModel):
    """Result of adding a player: the participant, their character, and invite link.

    The invite link is bound to (room, participant, character): opening it later
    resolves the player to exactly this character slot.
    """

    participant_id: uuid.UUID
    character_id: uuid.UUID
    role: ParticipantRole
    invite_link: InviteLinkResponse
