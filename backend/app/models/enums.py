"""Enumerations shared across ORM models."""

from __future__ import annotations

import enum


class ParticipantRole(enum.StrEnum):
    """A connected user is either the DM (host) or a player."""

    host = "host"
    player = "player"


class RoomStatus(enum.StrEnum):
    """Lifecycle of an encounter session."""

    lobby = "lobby"
    active = "active"
    ended = "ended"
