"""Per-room monotonic sequence numbers for broadcast Actions.

Each broadcast :class:`~app.schemas.action.Action` carries a ``seq`` so clients can
order and de-duplicate events. :class:`RoomSequencer` hands out a monotonically
increasing counter per room, starting at 0.

This is the ONLY live mutable server state introduced for action broadcasting; the
durable :class:`~app.models.token.Token` / :class:`~app.models.character.Character`
rows remain the board's source of truth (consistent with the established "read the
rows, no in-memory BoardState store" decision). One instance is created per
Socket.IO server in ``register_handlers`` and shared across that process; persisting
sequences across restarts / scaling past one process is a later (Phase 7) concern.
"""

from __future__ import annotations


class RoomSequencer:
    """Vends a per-room monotonic, zero-based sequence number."""

    def __init__(self) -> None:
        self._next: dict[str, int] = {}

    def next_seq(self, room_id: str) -> int:
        """Return this room's next sequence number and advance the counter."""
        current = self._next.get(room_id, 0)
        self._next[room_id] = current + 1
        return current
