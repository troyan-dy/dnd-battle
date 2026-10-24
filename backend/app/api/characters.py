"""Room character API router — read the room's character stat blocks."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.api.dependencies import SessionDep, not_found, require_room, rooms_router
from app.models.character import Character
from app.schemas.character import CharacterResponse

router = rooms_router()


@router.get("/{room_id}/characters", response_model=list[CharacterResponse])
async def list_characters(
    room_id: uuid.UUID,
    session: SessionDep,
) -> list[CharacterResponse]:
    """List every character in the room (reconnect-safe: a plain idempotent read).

    This is what the board uses to hydrate token display data (name, HP,
    conditions) in a single request, instead of one ``get_character`` call per
    token. No auth gate yet — consistent with the rest of the room read API (the
    link is the credential; server-enforced permissions are the Phase 7 task).
    Returns 404 if the room is unknown.
    """
    await require_room(session, room_id)

    in_room = select(Character).where(Character.room_id == room_id)
    characters = await session.scalars(in_room)
    return [CharacterResponse.model_validate(character) for character in characters]


@router.get("/{room_id}/characters/{character_id}", response_model=CharacterResponse)
async def get_character(
    room_id: uuid.UUID,
    character_id: uuid.UUID,
    session: SessionDep,
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
        raise not_found("Character not found.")
    return CharacterResponse.model_validate(character)
