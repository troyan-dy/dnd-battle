"""Room API router — host creates a room and adds / revokes its participants.

Flow for ``POST /rooms`` (host action; no auth gate yet — the host link *is* the
credential, see CLAUDE.md Phase 1):

1. Insert the :class:`Room` (status ``lobby``).
2. Insert the host :class:`Participant` (``role=host``, no character slot).
3. Mint an unguessable invite token, store only its SHA-256 hash on an
   :class:`InviteLink` bound to (room, host), and return the plaintext **once**.

The plaintext token never touches the DB; resolution (a later task) re-hashes an
incoming token and matches the unique ``token_hash``.

The rest of the room API lives in sibling routers under the same ``/rooms``
prefix: :mod:`app.api.maps`, :mod:`app.api.characters`, :mod:`app.api.tokens` and
:mod:`app.api.initiative`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import status
from sqlalchemy import select

from app.api.dependencies import SessionDep, not_found, require_room, rooms_router
from app.models import Character, InviteLink, Participant, ParticipantRole, Room
from app.schemas.character import AddPlayerRequest, AddPlayerResponse
from app.schemas.invite import RevokeLinksResponse
from app.schemas.room import CreateRoomRequest, CreateRoomResponse, RoomSummary
from app.services.invites import mint_invite

router = rooms_router()


@router.post("", response_model=CreateRoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: CreateRoomRequest,
    session: SessionDep,
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

    host_link = mint_invite(session, room_id=room.id, participant_id=host.id)

    await session.commit()

    return CreateRoomResponse(
        room=RoomSummary.model_validate(room),
        host_participant_id=host.id,
        host_role=host.role,
        host_link=host_link,
    )


@router.post(
    "/{room_id}/participants",
    response_model=AddPlayerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_player(
    room_id: uuid.UUID,
    payload: AddPlayerRequest,
    session: SessionDep,
) -> AddPlayerResponse:
    """Host action: add a player bound to a new character slot, minting their link.

    Each call creates a *new* :class:`Character` slot, a player :class:`Participant`
    bound to it, and a fresh unguessable :class:`InviteLink`. The plaintext token is
    returned **once**; only its SHA-256 hash is persisted (same scheme as the host
    link). Calling the endpoint again mints a distinct token — never reused.
    """
    room = await require_room(session, room_id)

    character = Character(
        room_id=room.id,
        name=payload.character_name,
        max_hp=payload.max_hp,
        current_hp=payload.max_hp,
        armor_class=payload.armor_class,
        ability_scores=payload.ability_scores.model_dump(),
        resistances=payload.resistances,
        portrait_url=payload.portrait_url,
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

    invite_link = mint_invite(session, room_id=room.id, participant_id=player.id)

    await session.commit()

    return AddPlayerResponse(
        participant_id=player.id,
        character_id=character.id,
        role=player.role,
        invite_link=invite_link,
    )


@router.post(
    "/{room_id}/participants/{participant_id}/revoke",
    response_model=RevokeLinksResponse,
)
async def revoke_participant_links(
    room_id: uuid.UUID,
    participant_id: uuid.UUID,
    session: SessionDep,
) -> RevokeLinksResponse:
    """Host action: revoke (disable) all active invite links for a participant.

    Revocation is addressed by ``(room_id, participant_id)`` — never by the secret
    plaintext token — so the host can invalidate a *player's* link without knowing
    that player's secret (architect sign-off, Phase 1 link security).

    Sets ``revoked_at`` on every currently-active link for the participant; after
    this, :func:`app.api.invites.resolve_invite` returns the uniform 404 for those
    tokens. The operation is **idempotent**: a second call revokes ``0`` more,
    since already-revoked links are skipped. This is an explicit host action and
    is therefore reconnect-safe (it is never triggered by a client reload).

    Returns 404 if the room does not exist, or the participant does not exist /
    does not belong to this room.
    """
    participant = await session.get(Participant, participant_id)
    if participant is None or participant.room_id != room_id:
        raise not_found("Participant not found.")

    now = dt.datetime.now(dt.UTC)
    active_query = select(InviteLink).where(
        InviteLink.participant_id == participant_id,
        InviteLink.revoked_at.is_(None),
    )
    active_links = (await session.scalars(active_query)).all()
    for link in active_links:
        link.revoked_at = now

    await session.commit()

    return RevokeLinksResponse(revoked=len(active_links))
