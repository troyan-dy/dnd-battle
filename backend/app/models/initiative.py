"""InitiativeEntry ORM model — one combatant's slot in a room's turn order.

The initiative tracker is DURABLE, server-authoritative state (CLAUDE.md rule 2):
a client that reloads its invite link mid-encounter must see the full turn order
AND whose turn it is, so the order cannot live only in memory. Each row is one
combatant in a room's order; the WHOSE-turn pointer (active index + round) lives on
the :class:`Room`.

``character_id`` is optional so a combatant need not be a player character (the host
can add NPCs / monster groups that have no :class:`Character` stat block); ``name``
carries the display label either way. ``order_index`` is the resolved 0-based seat in
the turn order (entries are sorted by ``initiative`` descending when the host sets the
tracker), so reading the order back is a plain ``ORDER BY order_index``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.room import Room


class InitiativeEntry(Base, TimestampMixin):
    """A single combatant's seat in a room's initiative / turn order."""

    __tablename__ = "initiative_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Optional binding to a character stat block; NULL for NPC/monster combatants.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    # Display label shown in the tracker (the character or monster name).
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The rolled initiative value (higher acts first); ties resolved by order_index.
    initiative: Mapped[int] = mapped_column(Integer, nullable=False)
    # Resolved 0-based seat in the turn order (sorted by initiative desc on set).
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    room: Mapped[Room] = relationship(back_populates="initiative_entries")
    character: Mapped[Character | None] = relationship()
