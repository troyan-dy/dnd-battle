"""Pydantic contracts for the initiative / turn-order tracker.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.limits import NAME_MAX_LENGTH

# Initiative roll bounds. A d20 initiative + modifiers realistically stays well
# within these; we cap to reject abusive values while allowing big negatives.
INITIATIVE_MIN = -50
INITIATIVE_MAX = 100
# A host may seat at most this many combatants in one turn order.
INITIATIVE_MAX_ENTRIES = 100


class InitiativeEntryInput(BaseModel):
    """One combatant the host seats in the turn order when setting initiative.

    Either bind it to an existing ``character_id`` (which must belong to the room)
    or leave it ``None`` for an NPC/monster; ``name`` is the display label shown in
    the tracker. ``initiative`` is the rolled value (higher acts first).
    """

    character_id: uuid.UUID | None = Field(
        default=None, description="Character this combatant represents, or None for an NPC."
    )
    name: str = Field(
        min_length=1, max_length=NAME_MAX_LENGTH, description="Display label in the tracker."
    )
    initiative: int = Field(
        ge=INITIATIVE_MIN, le=INITIATIVE_MAX, description="Rolled initiative (higher acts first)."
    )


class SetInitiativeRequest(BaseModel):
    """Host's request to (re)build a room's initiative order.

    Replaces any existing order. Entries are sorted by ``initiative`` descending
    (ties broken stably by the order given); the active turn resets to the first
    combatant and the round counter resets to 1.
    """

    entries: list[InitiativeEntryInput] = Field(
        default_factory=list,
        max_length=INITIATIVE_MAX_ENTRIES,
        description="Combatants to seat in the turn order (empty clears it).",
    )


class InitiativeEntryResponse(BaseModel):
    """Read view of one combatant's seat in the turn order."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    character_id: uuid.UUID | None
    name: str
    initiative: int
    order_index: int


class InitiativeState(BaseModel):
    """The full turn-order snapshot: the ordered combatants + whose turn it is.

    ``active_index`` is the 0-based seat whose turn it currently is (``None`` when
    no order is set = combat not started); ``round`` counts rounds. Part of the
    reconnect-safe :class:`BoardState`, so a client that reloads its link rebuilds
    the tracker exactly (CLAUDE.md rule 2).
    """

    active_index: int | None
    round: int
    entries: list[InitiativeEntryResponse]
