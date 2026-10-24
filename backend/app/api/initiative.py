"""Room initiative API router — set and read the turn order."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import SessionDep, require_room, rooms_router, unprocessable
from app.models.character import Character
from app.schemas.initiative import InitiativeEntryInput, InitiativeState, SetInitiativeRequest
from app.services.initiative import build_initiative_state, set_initiative

router = rooms_router()


@router.put("/{room_id}/initiative", response_model=InitiativeState)
async def put_initiative(
    room_id: uuid.UUID,
    payload: SetInitiativeRequest,
    session: SessionDep,
) -> InitiativeState:
    """Host action: (re)build the room's initiative / turn order.

    Replaces any existing order. The combatants are sorted by initiative descending
    (ties stable by the order given), the active turn resets to the first seat and
    the round to 1. An empty ``entries`` list clears the tracker. Same established
    host-action pattern (no auth gate yet) as token placement.

    Each entry may bind a ``character_id`` (which must belong to this room → 422) or
    leave it ``None`` for an NPC/monster combatant. Returns 404 if the room is
    unknown. The realtime ``endTurn`` action then advances this order live.
    """
    room = await require_room(session, room_id)
    await _require_room_characters(session, room_id=room_id, entries=payload.entries)

    state = await set_initiative(session, room=room, entries=payload.entries)
    await session.commit()
    return state


@router.get("/{room_id}/initiative", response_model=InitiativeState)
async def get_initiative(
    room_id: uuid.UUID,
    session: SessionDep,
) -> InitiativeState:
    """Read the room's current initiative order (reconnect-safe idempotent read).

    Returns 404 if the room is unknown. The same snapshot is also embedded in the
    realtime ``boardState`` push on (re)join.
    """
    await require_room(session, room_id)

    return await build_initiative_state(session, room_id)


async def _require_room_characters(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    entries: list[InitiativeEntryInput],
) -> None:
    """Every character an entry binds must exist in ``room_id`` (else 422)."""
    character_ids = {entry.character_id for entry in entries if entry.character_id is not None}
    if not character_ids:
        return
    in_room = select(Character.id).where(
        Character.id.in_(character_ids),
        Character.room_id == room_id,
    )
    found_ids = set(await session.scalars(in_room))
    if found_ids != character_ids:
        raise unprocessable("Initiative entry references a character not in this room.")
