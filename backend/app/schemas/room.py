"""Pydantic request/response contracts for creating a room and its map.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
Invite-link plaintext appears in a response model exactly once — when the room
is created — and is never persisted (only its SHA-256 hash is, server-side).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.limits import NAME_MAX_LENGTH
from app.models.enums import ParticipantRole, RoomStatus
from app.schemas.invite import InviteLinkResponse


class CreateRoomRequest(BaseModel):
    """Host's request to open a new encounter session."""

    name: str = Field(
        min_length=1, max_length=NAME_MAX_LENGTH, description="Encounter / room name."
    )
    host_display_name: str | None = Field(
        default=None,
        max_length=NAME_MAX_LENGTH,
        description="Optional friendly name shown for the DM.",
    )


class RoomSummary(BaseModel):
    """Public view of a freshly created room."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: RoomStatus


class CreateRoomResponse(BaseModel):
    """Result of creating a room: the room, the host participant, and host link."""

    room: RoomSummary
    host_participant_id: uuid.UUID
    host_role: ParticipantRole
    host_link: InviteLinkResponse


class MapResponse(BaseModel):
    """Result of uploading (or describing) a room's current map image.

    ``url`` is the server path that streams the stored image back
    (``GET /rooms/{room_id}/map``); the bytes themselves are never inlined here.
    """

    room_id: uuid.UUID
    content_type: str = Field(description="Validated image MIME type of the stored map.")
    url: str = Field(description="Path that serves the map image: /rooms/{room_id}/map.")
