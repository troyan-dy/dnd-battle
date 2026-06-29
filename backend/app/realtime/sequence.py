"""Per-room monotonic sequence numbers for broadcast Actions.

Each broadcast :class:`~app.schemas.action.Action` carries a ``seq`` so clients can
order and de-duplicate events. :class:`RoomSequencer` hands out a monotonically
increasing counter per room, starting at 0.

The in-memory counter is a fast cache, not the source of truth: the high-water mark
is persisted on ``Room.last_action_seq`` (see
:func:`app.services.actions.reserve_action_seq`). A freshly started process seeds the
counter from that durable value via :meth:`RoomSequencer.seed` before vending, so the
action sequence survives a server restart rather than colliding from 0 (CLAUDE.md
rule 2). The durable :class:`~app.models.token.Token` /
:class:`~app.models.character.Character` rows remain the board's source of truth
(consistent with the established "read the rows, no in-memory BoardState store"
decision). One instance is created per Socket.IO server in ``register_handlers`` and
shared across that process.
"""

from __future__ import annotations


class RoomSequencer:
    """Vends a per-room monotonic, zero-based sequence number."""

    def __init__(self) -> None:
        self._next: dict[str, int] = {}

    def seed(self, room_id: str, next_seq: int) -> None:
        """Recover a room's counter from its durable high-water mark.

        Sets the next sequence number to issue for ``room_id`` to ``next_seq`` when
        this process has not yet tracked the room (e.g. right after a restart), or
        when the persisted value is ahead of the in-memory one. Never moves the
        counter backwards, so it is idempotent and safe to call on every action.
        """
        existing = self._next.get(room_id)
        if existing is None or next_seq > existing:
            self._next[room_id] = next_seq

    def next_seq(self, room_id: str) -> int:
        """Return this room's next sequence number and advance the counter."""
        current = self._next.get(room_id, 0)
        self._next[room_id] = current + 1
        return current
