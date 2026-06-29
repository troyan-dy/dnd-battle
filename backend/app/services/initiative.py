"""Initiative / turn-order service — durable, server-authoritative turn tracking.

The tracker is the source of truth for WHOSE turn it is (CLAUDE.md rule 1) and must
survive a reconnect (rule 2), so it lives in the database: ordered
:class:`InitiativeEntry` rows plus a pointer (``initiative_active_index`` +
``initiative_round``) on the :class:`Room`.

Three pure-ish operations (all read/mutate rows; the caller commits):

* :func:`set_initiative` — the host (re)builds the order. Replaces any existing
  entries, sorts the given combatants by initiative descending (ties broken stably
  by input order), seats them at ``order_index`` 0..n-1, resets the active turn to
  the first seat and the round to 1.
* :func:`advance_turn` — the ``endTurn`` action. Moves the active pointer to the
  next seat; wrapping past the last seat resets to 0 and increments the round.
  A no-op when no order is set.
* :func:`build_initiative_state` — read the full :class:`InitiativeState` snapshot
  for the reconnect-safe BoardState.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.initiative import InitiativeEntry
from app.models.room import Room
from app.schemas.room import (
    InitiativeEntryInput,
    InitiativeEntryResponse,
    InitiativeState,
)


async def set_initiative(
    session: AsyncSession,
    *,
    room: Room,
    entries: list[InitiativeEntryInput],
) -> InitiativeState:
    """Replace ``room``'s turn order with ``entries`` (sorted by initiative desc).

    Deletes the room's existing initiative rows (config replacement, the explicit
    purpose of this call — not user-content deletion), reseats the combatants, and
    resets the active turn to the first seat (``None`` when ``entries`` is empty)
    with the round counter back to 1. The caller commits.
    """
    await session.execute(delete(InitiativeEntry).where(InitiativeEntry.room_id == room.id))

    # Sort by initiative descending; Python's sort is stable so ties keep input order.
    ordered = sorted(entries, key=lambda e: e.initiative, reverse=True)
    for index, entry in enumerate(ordered):
        session.add(
            InitiativeEntry(
                room_id=room.id,
                character_id=entry.character_id,
                name=entry.name,
                initiative=entry.initiative,
                order_index=index,
            )
        )

    room.initiative_active_index = 0 if ordered else None
    room.initiative_round = 1

    await session.flush()
    return await build_initiative_state(session, room.id)


async def advance_turn(session: AsyncSession, *, room: Room) -> None:
    """Advance ``room``'s active turn to the next combatant (``endTurn``).

    Wrapping past the last seat resets to the first seat and increments the round.
    A no-op when no order is set (no entries / ``active_index`` is ``None``). The
    caller commits.
    """
    count = await _entry_count(session, room.id)
    if count == 0 or room.initiative_active_index is None:
        return

    next_index = room.initiative_active_index + 1
    if next_index >= count:
        next_index = 0
        room.initiative_round += 1
    room.initiative_active_index = next_index


async def build_initiative_state(session: AsyncSession, room_id: uuid.UUID) -> InitiativeState:
    """Assemble the full :class:`InitiativeState` snapshot for ``room_id``."""
    room = await session.get(Room, room_id)
    entries = (
        (
            await session.execute(
                select(InitiativeEntry)
                .where(InitiativeEntry.room_id == room_id)
                .order_by(InitiativeEntry.order_index)
            )
        )
        .scalars()
        .all()
    )
    return InitiativeState(
        active_index=room.initiative_active_index if room is not None else None,
        round=room.initiative_round if room is not None else 1,
        entries=[InitiativeEntryResponse.model_validate(e) for e in entries],
    )


async def active_character_id(session: AsyncSession, room: Room) -> uuid.UUID | None:
    """Return the character_id of the combatant whose turn it is, or ``None``.

    ``None`` when combat has not started, the active seat is out of range, or the
    active combatant is an NPC with no bound character. Used by the action gate to
    decide whether a given player may end the current turn.
    """
    if room.initiative_active_index is None:
        return None
    entry = (
        await session.execute(
            select(InitiativeEntry).where(
                InitiativeEntry.room_id == room.id,
                InitiativeEntry.order_index == room.initiative_active_index,
            )
        )
    ).scalar_one_or_none()
    return entry.character_id if entry is not None else None


async def _entry_count(session: AsyncSession, room_id: uuid.UUID) -> int:
    entries = (
        (
            await session.execute(
                select(InitiativeEntry.id).where(InitiativeEntry.room_id == room_id)
            )
        )
        .scalars()
        .all()
    )
    return len(entries)
