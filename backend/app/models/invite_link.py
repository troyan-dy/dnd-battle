"""InviteLink ORM model — unguessable, revocable, single-purpose access tokens.

Security design (architect sign-off, Phase 1):

* **Never store plaintext.** Only the SHA-256 ``token_hash`` is persisted, so a
  database leak cannot reveal live links. The plaintext is shown to the host once
  at creation time (token generation lands in the "Link security" task).
* **Unguessable.** Tokens are generated with high entropy (``secrets``); this
  table only stores their hash, which is ``unique`` + indexed for O(1) lookup.
* **Revocable.** ``revoked_at`` is set to disable a link; reissuing creates a new
  row instead of mutating the old one (history is preserved, no plaintext recovery).
* **Single-purpose / time-bound.** ``expires_at`` and ``used_at`` bound a link's
  validity. Active == ``revoked_at IS NULL AND (expires_at IS NULL OR now < expires_at)``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.participant import Participant
    from app.models.room import Room


class InviteLink(Base, TimestampMixin):
    """A per-participant access credential. Resolves to (room, participant, character)."""

    __tablename__ = "invite_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # SHA-256 hex digest of the plaintext token. Unique so lookups are exact and
    # so the same token can never be registered twice.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    room: Mapped[Room] = relationship(back_populates="invite_links")
    participant: Mapped[Participant] = relationship(back_populates="invite_links")
