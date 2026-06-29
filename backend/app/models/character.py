"""Character ORM model — a D&D 2024 stat block owned within a room."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON as SAJSON
from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.participant import Participant
    from app.models.room import Room
    from app.models.token import Token


class Character(Base, TimestampMixin):
    """A character/monster stat block. Token board coords live in BoardState."""

    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    current_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    # Armor Class — the target number an attack roll must meet to hit (2024 PHB).
    # Defaults to 10 (the unarmored baseline); the rules engine bounds it 1..50.
    armor_class: Mapped[int] = mapped_column(
        Integer, default=10, server_default="10", nullable=False
    )
    # Damage resistances/vulnerabilities/immunities keyed by damage type
    # (e.g. {"fire": "resistance"}); an absent type means a normal relationship.
    resistances: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict, nullable=False)
    # Optional portrait image URL (DM-provided). A full upload pipeline can replace
    # this later; a plain URL keeps the value reconnect-safe and storage-free.
    portrait_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Ability scores keyed by short name (str/dex/...); defaulted by rules layer.
    ability_scores: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict, nullable=False)
    # Active condition names (2024 list); effects live in the rules engine.
    conditions: Mapped[list[str]] = mapped_column(SAJSON, default=list, nullable=False)

    room: Mapped[Room] = relationship(back_populates="characters")
    owner: Mapped[Participant | None] = relationship(back_populates="character")
    # At most one board token per character (placed by the host).
    token: Mapped[Token | None] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
