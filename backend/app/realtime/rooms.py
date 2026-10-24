"""Socket.IO room naming for a D&D board room and its role-specific sub-rooms."""

from __future__ import annotations

from app.models.enums import ParticipantRole

# Socket.IO rooms share a flat namespace per server; prefix the D&D Room id so
# board rooms can never collide with any other room name we introduce later.
ROOM_PREFIX = "room:"


def room_name(room_id: str) -> str:
    """Return the Socket.IO room name mirroring a given D&D ``Room`` id."""
    return f"{ROOM_PREFIX}{room_id}"


def host_room_name(room_id: str) -> str:
    """Sub-room holding only the room's HOST connections (fog-of-war broadcasts).

    A host is in BOTH the base room and this sub-room; a player is only in the base
    room (+ the player sub-room). Emitting to this sub-room reaches hosts ONLY, so
    a hidden token's movement / HP and visibility changes never leak to players.
    """
    return f"{ROOM_PREFIX}{room_id}:host"


def player_room_name(room_id: str) -> str:
    """Sub-room holding only the room's PLAYER connections (filtered resyncs)."""
    return f"{ROOM_PREFIX}{room_id}:player"


def role_room_name(room_id: str, role: ParticipantRole) -> str:
    """The role-specific sub-room a connection joins alongside the base room."""
    if role == ParticipantRole.host:
        return host_room_name(room_id)
    return player_room_name(room_id)
