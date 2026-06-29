"""Room API router — host creates a room and receives the host invite link.

Flow for ``POST /rooms`` (host action; no auth gate yet — the host link *is* the
credential, see CLAUDE.md Phase 1):

1. Insert the :class:`Room` (status ``lobby``).
2. Insert the host :class:`Participant` (``role=host``, no character slot).
3. Mint an unguessable invite token, store only its SHA-256 hash on an
   :class:`InviteLink` bound to (room, host), and return the plaintext **once**.

The plaintext token never touches the DB; resolution (a later task) re-hashes an
incoming token and matches the unique ``token_hash``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import APP_BASE_URL
from app.db.session import get_session
from app.models.character import Character
from app.models.enums import ParticipantRole
from app.models.invite_link import InviteLink
from app.models.participant import Participant
from app.models.room import Room
from app.schemas.room import (
    AddPlayerRequest,
    AddPlayerResponse,
    CreateRoomRequest,
    CreateRoomResponse,
    InviteLinkResponse,
    RoomSummary,
)
from app.security.tokens import generate_token, hash_token

router = APIRouter(prefix="/rooms", tags=["rooms"])


def build_invite_url(token: str) -> str:
    """Return the shareable join URL for a plaintext invite token."""
    return f"{APP_BASE_URL}/join/{token}"


@router.post("", response_model=CreateRoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: CreateRoomRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreateRoomResponse:
    """Create a room and its host participant, returning the host invite link."""
    room = Room(name=payload.name)
    session.add(room)
    await session.flush()  # assign room.id

    host = Participant(
        room_id=room.id,
        role=ParticipantRole.host,
        display_name=payload.host_display_name,
    )
    session.add(host)
    await session.flush()  # assign host.id

    token = generate_token()
    invite = InviteLink(
        room_id=room.id,
        participant_id=host.id,
        token_hash=hash_token(token),
    )
    session.add(invite)

    await session.commit()

    return CreateRoomResponse(
        room=RoomSummary.model_validate(room),
        host_participant_id=host.id,
        host_role=host.role,
        host_link=InviteLinkResponse(token=token, url=build_invite_url(token)),
    )


@router.post(
    "/{room_id}/participants",
    response_model=AddPlayerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_player(
    room_id: uuid.UUID,
    payload: AddPlayerRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AddPlayerResponse:
    """Host action: add a player bound to a new character slot, minting their link.

    Each call creates a *new* :class:`Character` slot, a player :class:`Participant`
    bound to it, and a fresh unguessable :class:`InviteLink`. The plaintext token is
    returned **once**; only its SHA-256 hash is persisted (same scheme as the host
    link). Calling the endpoint again mints a distinct token — never reused.
    """
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")

    character = Character(
        room_id=room.id,
        name=payload.character_name,
        max_hp=payload.max_hp,
        current_hp=payload.max_hp,
    )
    session.add(character)
    await session.flush()  # assign character.id

    player = Participant(
        room_id=room.id,
        role=ParticipantRole.player,
        display_name=payload.display_name,
        character_id=character.id,
    )
    session.add(player)
    await session.flush()  # assign player.id

    token = generate_token()
    invite = InviteLink(
        room_id=room.id,
        participant_id=player.id,
        token_hash=hash_token(token),
    )
    session.add(invite)

    await session.commit()

    return AddPlayerResponse(
        participant_id=player.id,
        character_id=character.id,
        role=player.role,
        invite_link=InviteLinkResponse(token=token, url=build_invite_url(token)),
    )
