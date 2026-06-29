"""Room ORM model — a single encounter session."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import RoomStatus

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.initiative import InitiativeEntry
    from app.models.invite_link import InviteLink
    from app.models.participant import Participant
    from app.models.token import Token


class Room(Base, TimestampMixin):
    """An encounter session: owns participants, characters, and invite links."""

    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[RoomStatus] = mapped_column(
        SAEnum(RoomStatus, name="room_status"),
        default=RoomStatus.lobby,
        nullable=False,
    )
    # Current encounter map, if any. ``map_image_path`` is the server-generated
    # filename within ``MAP_STORAGE_DIR`` (never a client-supplied path);
    # ``map_content_type`` is the validated, allowlisted image MIME type. Both
    # are NULL until the host uploads a map; a re-upload overwrites them.
    map_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    map_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Initiative / turn-order pointer (CLAUDE.md BoardState). The ordered combatant
    # rows live in ``initiative_entries``; these two columns track WHOSE turn it is.
    # ``initiative_active_index`` is the 0-based position in that order (NULL until
    # the host sets an order = combat not started); ``initiative_round`` counts the
    # rounds, incremented each time the active pointer wraps past the last combatant.
    initiative_active_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initiative_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Durable high-water mark for the per-room broadcast Action ``seq`` (the next
    # sequence number to issue, zero-based). Persisting it here means the action
    # sequence survives a server restart: a freshly started process seeds its
    # in-memory counter from this column instead of colliding from 0, so clients
    # keep ordering/de-duplicating broadcasts correctly (CLAUDE.md rule 2).
    last_action_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    participants: Mapped[list[Participant]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
    characters: Mapped[list[Character]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
    invite_links: Mapped[list[InviteLink]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
    tokens: Mapped[list[Token]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
    initiative_entries: Mapped[list[InitiativeEntry]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
