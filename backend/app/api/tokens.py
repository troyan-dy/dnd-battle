"""Room token API router — place, list and reposition the board's tokens."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    SessionDep,
    not_found,
    require_room,
    rooms_router,
    unprocessable,
)
from app.models.character import Character
from app.models.token import Token
from app.schemas.token import PlaceTokenRequest, TokenResponse, UpdateTokenRequest

router = rooms_router()


@router.post(
    "/{room_id}/tokens",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def place_token(
    room_id: uuid.UUID,
    payload: PlaceTokenRequest,
    session: SessionDep,
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
    await require_room(session, room_id)
    await _require_room_character(session, room_id=room_id, character_id=payload.character_id)
    await _require_no_token(session, character_id=payload.character_id)

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
    session: SessionDep,
) -> list[TokenResponse]:
    """List every token in the room (reconnect-safe: a plain idempotent read).

    This is what a (re)connecting client uses to draw the current board placement
    before realtime sync (Phase 4) takes over. Returns 404 if the room is unknown.
    """
    await require_room(session, room_id)

    in_room = select(Token).where(Token.room_id == room_id)
    tokens = await session.scalars(in_room)
    return [TokenResponse.model_validate(token) for token in tokens]


@router.patch("/{room_id}/tokens/{token_id}", response_model=TokenResponse)
async def update_token(
    room_id: uuid.UUID,
    token_id: uuid.UUID,
    payload: UpdateTokenRequest,
    session: SessionDep,
) -> TokenResponse:
    """Host action: reposition / resize an existing token.

    Only the provided fields change; at least one must be supplied (else 422).
    Returns 404 if the token does not exist or does not belong to this room.
    """
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise unprocessable("Provide at least one of x, y, size.")

    token = await session.get(Token, token_id)
    if token is None or token.room_id != room_id:
        raise not_found("Token not found.")

    for field_name, field_value in fields.items():
        setattr(token, field_name, field_value)
    await session.commit()
    await session.refresh(token)

    return TokenResponse.model_validate(token)


async def _require_room_character(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    character_id: uuid.UUID,
) -> None:
    """The character must exist (else 404) and belong to ``room_id`` (else 422)."""
    character = await session.get(Character, character_id)
    if character is None:
        raise not_found("Character not found.")
    if character.room_id != room_id:
        raise unprocessable("Character does not belong to this room.")


async def _require_no_token(session: AsyncSession, *, character_id: uuid.UUID) -> None:
    """A character has at most one token: placing a second one is a 409 conflict."""
    by_character = select(Token).where(Token.character_id == character_id)
    existing = (await session.execute(by_character)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Character already has a token; reposition it instead.",
        )
