"""Participant ORM model — a connected user bound to a room (and a character)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ParticipantRole

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.invite_link import InviteLink
    from app.models.room import Room


class Participant(Base, TimestampMixin):
    """A user in a room. ``host`` (DM) or ``player`` bound to one character slot."""

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[ParticipantRole] = mapped_column(
        SAEnum(ParticipantRole, name="participant_role"),
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # The character this participant controls (a host may have none).
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )

    room: Mapped[Room] = relationship(back_populates="participants")
    character: Mapped[Character | None] = relationship(back_populates="owner")
    invite_links: Mapped[list[InviteLink]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )
