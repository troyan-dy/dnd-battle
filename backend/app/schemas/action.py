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

from app.rules.dice import D20_SIDES, DiceExpressionError, parse_dice
from app.schemas.room import GRID_COORD_MAX, GRID_COORD_MIN

# Current Action-protocol version. Clients stamp this on every intent; the server
# rejects anything it does not support. Bump on an incompatible change.
ACTION_PROTOCOL_VERSION = 1

# Damage / healing magnitudes. Capped at the max-HP ceiling (room.AddPlayerRequest
# limits max_hp to 1000) so a single action can never apply an absurd amount.
DAMAGE_AMOUNT_MIN = 1
DAMAGE_AMOUNT_MAX = 1000
HEAL_AMOUNT_MIN = 1
HEAL_AMOUNT_MAX = 1000

# Cosmetic bounds for a board mark/ping.
MARK_LABEL_MAX_LENGTH = 60
MARK_COLOR_MAX_LENGTH = 32

# Attack bounds: a flat to-hit bonus and the max length of a damage dice expression.
ATTACK_BONUS_MIN = -20
ATTACK_BONUS_MAX = 20
DAMAGE_EXPR_MAX_LENGTH = 32
DEFAULT_ATTACK_DAMAGE = "1d6"


class ActionType(enum.StrEnum):
    """Discriminator values for the per-action payloads."""

    MOVE = "move"
    MARK = "mark"
    DAMAGE = "damage"
    HEAL = "heal"
    ATTACK = "attack"
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
    """Apply damage to a token, reducing its character's HP (clamped at 0).

    Damage and healing are deliberately SEPARATE action types (not one signed
    amount): the discriminated union is additive, so they parse independently and
    stay semantically distinct for the upcoming combat log.
    """

    type: Literal[ActionType.DAMAGE] = ActionType.DAMAGE
    token_id: uuid.UUID = Field(description="Token taking damage.")
    amount: int = Field(
        ge=DAMAGE_AMOUNT_MIN, le=DAMAGE_AMOUNT_MAX, description="Hit points of damage to apply."
    )


class HealPayload(BaseModel):
    """Heal a token, restoring its character's HP (clamped at its max HP).

    The mirror of :class:`DamagePayload`: a positive ``amount`` of hit points
    added back, never exceeding the character's maximum.
    """

    type: Literal[ActionType.HEAL] = ActionType.HEAL
    token_id: uuid.UUID = Field(description="Token being healed.")
    amount: int = Field(
        ge=HEAL_AMOUNT_MIN, le=HEAL_AMOUNT_MAX, description="Hit points of healing to apply."
    )


class AttackIntentPayload(BaseModel):
    """Client → server: an attack from one token against another (Phase 5).

    Carries only the participants and the attacker's offence: a flat to-hit
    ``attack_bonus`` and a ``damage`` dice expression (e.g. ``"1d8+3"``). The d20
    attack roll and the damage roll are made by the SERVER (CLAUDE.md rule 1) and
    returned in :class:`AttackResultPayload`; the client never supplies a result,
    so this is an INTENT-only payload (it appears in the intent union, not the
    broadcast union).
    """

    type: Literal[ActionType.ATTACK] = ActionType.ATTACK
    attacker_token_id: uuid.UUID = Field(description="Token making the attack.")
    target_token_id: uuid.UUID = Field(description="Token being attacked.")
    attack_bonus: int = Field(
        default=0,
        ge=ATTACK_BONUS_MIN,
        le=ATTACK_BONUS_MAX,
        description="Flat bonus added to the d20 attack roll.",
    )
    damage: str = Field(
        default=DEFAULT_ATTACK_DAMAGE,
        max_length=DAMAGE_EXPR_MAX_LENGTH,
        description="Damage dice expression, e.g. '1d8+3'.",
    )

    @field_validator("damage")
    @classmethod
    def _check_damage(cls, value: str) -> str:
        """Reject a malformed / out-of-bounds dice expression at parse time."""
        try:
            parse_dice(value)
        except DiceExpressionError as exc:
            raise ValueError(str(exc)) from exc
        return value


class AttackResultPayload(BaseModel):
    """Server → all clients: the resolved outcome of an attack — the log line.

    Built by the server after rolling: the raw d20, the bonus + total, and the
    rolled damage breakdown applied to the target. This is what everyone sees in
    the shared combat log. It is BROADCAST-only (it never arrives as a client
    intent), so it appears in the broadcast union, not the intent union.

    Basic flow (Phase 5): the attack always lands and applies its damage. Hit/miss
    versus AC and advantage/disadvantage are the Phase-6 rules-engine task; the
    ``attack_total`` is already carried here so that step can gate on it later.
    """

    type: Literal[ActionType.ATTACK] = ActionType.ATTACK
    attacker_token_id: uuid.UUID = Field(description="Token that made the attack.")
    target_token_id: uuid.UUID = Field(description="Token that was attacked.")
    attack_roll: int = Field(ge=1, le=D20_SIDES, description="The raw d20 result (1..20).")
    attack_bonus: int = Field(description="Flat bonus added to the d20 roll.")
    attack_total: int = Field(description="attack_roll + attack_bonus.")
    damage: str = Field(description="The damage dice expression that was rolled.")
    damage_rolls: list[int] = Field(description="Each individual damage die result.")
    damage_total: int = Field(ge=0, description="Total damage applied to the target.")


class EndTurnPayload(BaseModel):
    """Advance the initiative order to the next combatant. Carries no data."""

    type: Literal[ActionType.END_TURN] = ActionType.END_TURN


# Discriminated unions of the concrete action payloads. Pydantic selects the member
# by the ``type`` field, so unknown / mismatched types fail to parse.
#
# Intent vs broadcast diverge ONLY for ``attack``: the client sends an
# :class:`AttackIntentPayload` (no roll), the server rolls and broadcasts an
# :class:`AttackResultPayload`. Every other action is identical in both directions.
IntentActionPayload = Annotated[
    MovePayload | MarkPayload | DamagePayload | HealPayload | AttackIntentPayload | EndTurnPayload,
    Field(discriminator="type"),
]
BroadcastActionPayload = Annotated[
    MovePayload | MarkPayload | DamagePayload | HealPayload | AttackResultPayload | EndTurnPayload,
    Field(discriminator="type"),
]
# Backward-compatible alias: an INTENT payload (what ``validate_intent`` returns).
ActionPayload = IntentActionPayload


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
    payload: IntentActionPayload

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
    payload: BroadcastActionPayload

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: int) -> int:
        return _validate_protocol_version(value)
