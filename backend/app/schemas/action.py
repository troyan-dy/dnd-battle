"""Versioned Action protocol — the realtime board event contract (CLAUDE.md).

An **Action** is a board change broadcast to everyone in a room: ``move``,
``mark``, ``damage``, ``endTurn`` … This module is the Pydantic *source of truth*
for those shapes (the TS client mirrors it).

Two envelopes encode CLAUDE.md architecture rule 1 ("server is authoritative;
clients send intents, the server validates and broadcasts the resulting Action"):

* :class:`ActionIntent` — **client → server**. Carries only the protocol
  ``version`` and the per-action ``payload``. It deliberately has *no* actor /
  room / id fields: those are stamped by the server from the authenticated
  connection so a client can never spoof who it is or what room it acts in.
* :class:`Action` — **server → all clients** in the room. The same ``payload``
  wrapped with server-generated metadata (``id``, ``room_id``,
  ``actor_participant_id``, monotonic ``seq``) for the broadcast.

Versioning: a single supported :data:`ACTION_PROTOCOL_VERSION`. The envelope's
``version`` field is validated, giving the server one clean place to refuse a
client whose protocol has drifted. Bump the constant and widen the check when an
incompatible change ships.

Per-action payloads form a **discriminated union** on their ``type`` field
(Pydantic ``Field(discriminator="type")``), so new action types are additive and
parse-time safe. This module is pure schema: it holds no live BoardState and does
no validation-against-state or broadcasting — those are separate Phase 4 tasks.
"""

from __future__ import annotations

import enum
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.room import GRID_COORD_MAX, GRID_COORD_MIN

# Current Action-protocol version. Clients stamp this on every intent; the server
# rejects anything it does not support. Bump on an incompatible change.
ACTION_PROTOCOL_VERSION = 1

# Damage / healing magnitudes. Capped at the max-HP ceiling (room.AddPlayerRequest
# limits max_hp to 1000) so a single action can never apply an absurd amount.
DAMAGE_AMOUNT_MIN = 1
DAMAGE_AMOUNT_MAX = 1000

# Cosmetic bounds for a board mark/ping.
MARK_LABEL_MAX_LENGTH = 60
MARK_COLOR_MAX_LENGTH = 32


class ActionType(enum.StrEnum):
    """Discriminator values for the per-action payloads."""

    MOVE = "move"
    MARK = "mark"
    DAMAGE = "damage"
    END_TURN = "endTurn"


class MovePayload(BaseModel):
    """Move a token to a grid cell. Bounds mirror the placement contract."""

    type: Literal[ActionType.MOVE] = ActionType.MOVE
    token_id: uuid.UUID = Field(description="Token being moved.")
    x: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Target grid column.")
    y: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Target grid row.")


class MarkPayload(BaseModel):
    """A transient mark / ping placed on the board for everyone to see."""

    type: Literal[ActionType.MARK] = ActionType.MARK
    x: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Mark grid column.")
    y: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Mark grid row.")
    color: str | None = Field(
        default=None, max_length=MARK_COLOR_MAX_LENGTH, description="Optional display color."
    )
    label: str | None = Field(
        default=None, max_length=MARK_LABEL_MAX_LENGTH, description="Optional short label."
    )


class DamagePayload(BaseModel):
    """Apply damage to a token. Healing rides the same shape with a separate type
    later; for now this is the unsigned-damage event named in Phase 5."""

    type: Literal[ActionType.DAMAGE] = ActionType.DAMAGE
    token_id: uuid.UUID = Field(description="Token taking damage.")
    amount: int = Field(
        ge=DAMAGE_AMOUNT_MIN, le=DAMAGE_AMOUNT_MAX, description="Hit points of damage to apply."
    )


class EndTurnPayload(BaseModel):
    """Advance the initiative order to the next combatant. Carries no data."""

    type: Literal[ActionType.END_TURN] = ActionType.END_TURN


# Discriminated union of every concrete action payload. Pydantic selects the
# member by the ``type`` field, so unknown / mismatched types fail to parse.
ActionPayload = Annotated[
    MovePayload | MarkPayload | DamagePayload | EndTurnPayload,
    Field(discriminator="type"),
]


def _validate_protocol_version(value: int) -> int:
    """Reject any envelope whose protocol version the server does not support."""
    if value != ACTION_PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported action protocol version {value!r}; "
            f"server supports {ACTION_PROTOCOL_VERSION}."
        )
    return value


class ActionIntent(BaseModel):
    """Client → server: a request to perform a board action.

    Intentionally minimal — the server derives *who* is acting and *which room*
    from the authenticated connection, never from this payload.
    """

    version: int = Field(
        default=ACTION_PROTOCOL_VERSION, description="Action-protocol version the client speaks."
    )
    payload: ActionPayload

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: int) -> int:
        return _validate_protocol_version(value)


class Action(BaseModel):
    """Server → all clients: the validated, broadcast board action.

    Wraps the same ``payload`` with server-stamped metadata. ``seq`` is a
    per-room monotonic counter clients can use to order / dedupe events.
    """

    version: int = Field(
        default=ACTION_PROTOCOL_VERSION, description="Action-protocol version of this broadcast."
    )
    id: uuid.UUID = Field(description="Server-generated unique id for this action.")
    room_id: uuid.UUID = Field(description="Room this action belongs to.")
    actor_participant_id: uuid.UUID = Field(
        description="Participant the server attributes this action to."
    )
    seq: int = Field(ge=0, description="Per-room monotonic sequence number.")
    payload: ActionPayload

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: int) -> int:
        return _validate_protocol_version(value)
