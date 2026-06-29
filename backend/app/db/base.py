"""Declarative base and shared column mixins for all ORM models.

A single ``Base`` (and therefore one ``Base.metadata``) is imported by every
model module so Alembic autogenerate and ``create_all`` see the full schema.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base; ``Base.metadata`` is the single source of truth."""


class TimestampMixin:
    """Adds server-managed ``created_at`` / ``updated_at`` timestamps (UTC)."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
