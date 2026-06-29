"""Room ORM model — a single encounter session."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import RoomStatus

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.invite_link import InviteLink
    from app.models.participant import Participant


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
