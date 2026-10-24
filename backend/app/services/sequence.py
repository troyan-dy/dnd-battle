"""Durable per-room broadcast ``seq`` allocation (survives a server restart).

The durable :attr:`Room.last_action_seq` column is the source of truth for the
next broadcast ``seq``; the realtime layer's in-memory sequencer is only a fast
cache seeded from it (CLAUDE.md rule 2).
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room


class SequenceCounter(Protocol):
    """Structural type for the in-memory per-room sequence cache.

    Declared here (rather than importing the concrete ``RoomSequencer`` from the
    realtime layer) so this service does not depend on the transport layer — the
    realtime layer already depends on this service, and importing back would create
    a cycle. :class:`app.realtime.sequence.RoomSequencer` satisfies it structurally.
    """

    def seed(self, room_id: str, next_seq: int) -> None:
        """Recover a room's counter from its durable high-water mark."""

    def next_seq(self, room_id: str) -> int:
        """Return this room's next sequence number and advance the counter."""


async def reserve_action_seq(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    sequencer: SequenceCounter,
) -> int:
    """Allocate the next broadcast ``seq`` for a room, persisting the high-water mark.

    The durable :class:`Room.last_action_seq` column is the source of truth so the
    action sequence survives a server restart (CLAUDE.md rule 2). The in-memory
    ``sequencer`` is a fast cache: it is first SEEDED from the persisted value (a
    no-op once this process is warm, but the recovery path after a restart), then
    asked for the next number; the row is bumped to the new high-water. The caller
    commits this in the SAME transaction as the action's durable effect, so a crash
    between applying the action and persisting its ``seq`` cannot occur.

    The ``None`` guard is defensive: the actor's identity came from a resolved invite
    so the room exists; if it somehow does not, fall back to the in-memory counter
    rather than fail mid-broadcast.
    """
    room_key = str(room_id)
    room = await session.get(Room, room_id)
    if room is None:
        return sequencer.next_seq(room_key)
    sequencer.seed(room_key, room.last_action_seq)
    seq = sequencer.next_seq(room_key)
    room.last_action_seq = seq + 1
    return seq
