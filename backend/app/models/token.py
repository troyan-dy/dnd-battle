"""Token ORM model — the on-board piece for a character (first BoardState piece).

A token is the durable, server-authoritative placement of a character on the
board grid. It carries grid coordinates ``(x, y)`` and a ``size`` in grid cells.
This persisted row is the source of truth that the in-memory live ``BoardState``
(Phase 4) hydrates from on connect, and that Phase 7 board snapshots build on.

Each token is bound to exactly one :class:`Character` (``character_id`` is
UNIQUE): a character has at most one token on the board. Placing a token for a
character that already has one is a conflict; repositioning updates the row.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.room import Room


class Token(Base, TimestampMixin):
    """A character's piece on the board grid: ``(x, y)`` coords + ``size`` in cells."""

    __tablename__ = "tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # One token per character (binds the piece to its stat block).
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    # Grid coordinates (column, row), 0-based; non-negative (validated in the API).
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    # Footprint in grid cells (1 = Tiny/Small/Medium, 2 = Large, 3 = Huge, ...).
    size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Fog of war: when True the host has HIDDEN this token. The server filters
    # hidden tokens (and their characters) out of the BoardState it pushes to
    # players, and never broadcasts their movement/HP to players (CLAUDE.md rule
    # 3 — enforced on the server). Only the host may toggle this. Durable so a
    # reconnecting client rebuilds the correct fog (CLAUDE.md rule 2).
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)

    room: Mapped[Room] = relationship(back_populates="tokens")
    character: Mapped[Character] = relationship(back_populates="token")
