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

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.config import APP_BASE_URL
from app.db.session import get_session
from app.models.character import Character
from app.models.enums import ParticipantRole
from app.models.invite_link import InviteLink
from app.models.participant import Participant
from app.models.room import Room
from app.models.token import Token
from app.schemas.room import (
    AddPlayerRequest,
    AddPlayerResponse,
    CharacterResponse,
    CreateRoomRequest,
    CreateRoomResponse,
    InviteLinkResponse,
    MapResponse,
    PlaceTokenRequest,
    RevokeLinksResponse,
    RoomSummary,
    TokenResponse,
    UpdateTokenRequest,
)
from app.security.tokens import generate_token, hash_token
from app.storage.maps import map_image_path, save_map_image

router = APIRouter(prefix="/rooms", tags=["rooms"])


def build_invite_url(token: str) -> str:
    """Return the shareable join URL for a plaintext invite token."""
    return f"{APP_BASE_URL}/join/{token}"


def build_map_url(room_id: uuid.UUID) -> str:
    """Return the path that streams a room's stored map image."""
    return f"/rooms/{room_id}/map"


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
        ability_scores=payload.ability_scores.model_dump(),
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


@router.post(
    "/{room_id}/participants/{participant_id}/revoke",
    response_model=RevokeLinksResponse,
)
async def revoke_participant_links(
    room_id: uuid.UUID,
    participant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.")

    now = dt.datetime.now(dt.UTC)
    active_links = (
        (
            await session.execute(
                select(InviteLink).where(
                    InviteLink.participant_id == participant_id,
                    InviteLink.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for link in active_links:
        link.revoked_at = now

    await session.commit()

    return RevokeLinksResponse(revoked=len(active_links))


@router.post(
    "/{room_id}/map",
    response_model=MapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_map(
    room_id: uuid.UUID,
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MapResponse:
    """Host action: upload (or replace) the room's encounter map image.

    No auth gate yet — this follows the same established host-action pattern as
    ``add_player``/``revoke`` (the link is the credential); server-enforced
    permissions are the explicit Phase 7 task. Validation guardrails:

    * the content type must be in the image allowlist (otherwise 415);
    * the body is read with a hard size cap (otherwise 413);
    * the file is stored under a *server-generated* name, so the client filename
      never influences the path (no traversal).

    Re-uploading overwrites the room's map pointer; the previous file is left on
    disk (cleanup is deferred — we never delete user content implicitly).
    """
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")

    content_type = file.content_type or ""
    if content_type not in config.MAP_CONTENT_TYPE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported map image type. Allowed: PNG, JPEG, WEBP, GIF.",
        )

    # Read at most the cap + 1 byte so an oversized upload never buffers unbounded.
    data = await file.read(config.MAX_MAP_UPLOAD_BYTES + 1)
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty map image upload.",
        )
    if len(data) > config.MAX_MAP_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Map image exceeds the maximum allowed size.",
        )

    filename = save_map_image(data, content_type)
    room.map_image_path = filename
    room.map_content_type = content_type
    await session.commit()

    return MapResponse(
        room_id=room.id,
        content_type=content_type,
        url=build_map_url(room.id),
    )


@router.get("/{room_id}/map")
async def get_map(
    room_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    """Serve a room's stored map image (reconnect-safe: a plain idempotent read).

    Returns 404 if the room has no map, or its stored file is missing on disk.
    """
    room = await session.get(Room, room_id)
    if room is None or room.map_image_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Map not found.")

    path = map_image_path(room.map_image_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Map not found.")

    return FileResponse(path, media_type=room.map_content_type or "application/octet-stream")


@router.get("/{room_id}/characters", response_model=list[CharacterResponse])
async def list_characters(
    room_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CharacterResponse]:
    """List every character in the room (reconnect-safe: a plain idempotent read).

    This is what the board uses to hydrate token display data (name, HP,
    conditions) in a single request, instead of one ``get_character`` call per
    token. No auth gate yet — consistent with the rest of the room read API (the
    link is the credential; server-enforced permissions are the Phase 7 task).
    Returns 404 if the room is unknown.
    """
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")

    characters = (
        (await session.execute(select(Character).where(Character.room_id == room_id)))
        .scalars()
        .all()
    )
    return [CharacterResponse.model_validate(c) for c in characters]


@router.get("/{room_id}/characters/{character_id}", response_model=CharacterResponse)
async def get_character(
    room_id: uuid.UUID,
    character_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CharacterResponse:
    """Read a single character's stat block (reconnect-safe idempotent read).

    The player view calls this after the invite resolves to a ``character_id`` to
    render the player's own character panel. No auth gate yet — consistent with the
    rest of the room read API (the link is the credential; server-enforced
    permissions are the explicit Phase 7 task). Returns 404 if the character is
    unknown or belongs to another room (cross-room guard).
    """
    character = await session.get(Character, character_id)
    if character is None or character.room_id != room_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    return CharacterResponse.model_validate(character)


@router.post(
    "/{room_id}/tokens",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def place_token(
    room_id: uuid.UUID,
    payload: PlaceTokenRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """Host action: place a token bound to a character on the board grid.

    This is the first piece of persisted (server-authoritative) BoardState: the
    in-memory live board (Phase 4) hydrates from these rows on connect. No auth
    gate yet — same established host-action pattern as ``add_player``/map upload.

    Validation:

    * the room must exist (404);
    * the character must exist *and belong to this room* (404 / 422), so a token
      can never be bound to another room's character;
    * a character has at most one token — placing a second one is a 409 conflict
      (reposition the existing token via ``PATCH`` instead);
    * grid coords and size are bounds-checked by the request schema.
    """
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")

    character = await session.get(Character, payload.character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    if character.room_id != room_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Character does not belong to this room.",
        )

    existing = (
        await session.execute(select(Token).where(Token.character_id == payload.character_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Character already has a token; reposition it instead.",
        )

    token = Token(
        room_id=room_id,
        character_id=payload.character_id,
        x=payload.x,
        y=payload.y,
        size=payload.size,
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)

    return TokenResponse.model_validate(token)


@router.get("/{room_id}/tokens", response_model=list[TokenResponse])
async def list_tokens(
    room_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TokenResponse]:
    """List every token in the room (reconnect-safe: a plain idempotent read).

    This is what a (re)connecting client uses to draw the current board placement
    before realtime sync (Phase 4) takes over. Returns 404 if the room is unknown.
    """
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")

    tokens = (await session.execute(select(Token).where(Token.room_id == room_id))).scalars().all()
    return [TokenResponse.model_validate(t) for t in tokens]


@router.patch("/{room_id}/tokens/{token_id}", response_model=TokenResponse)
async def update_token(
    room_id: uuid.UUID,
    token_id: uuid.UUID,
    payload: UpdateTokenRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """Host action: reposition / resize an existing token.

    Only the provided fields change; at least one must be supplied (else 422).
    Returns 404 if the token does not exist or does not belong to this room.
    """
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of x, y, size.",
        )

    token = await session.get(Token, token_id)
    if token is None or token.room_id != room_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")

    for key, value in fields.items():
        setattr(token, key, value)
    await session.commit()
    await session.refresh(token)

    return TokenResponse.model_validate(token)
