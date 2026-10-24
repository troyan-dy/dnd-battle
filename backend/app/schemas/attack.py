"""Attack payloads of the versioned Action protocol (Phase 5 / 6).

The client sends an :class:`AttackIntentPayload` (no roll); the server rolls and
broadcasts an :class:`AttackResultPayload`. This module is pure schema: the
Pydantic *source of truth* the TS client mirrors.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.rules.attack import Advantage
from app.rules.damage import DamageType, Defense
from app.rules.dice import D20_SIDES, DiceExpressionError, parse_dice
from app.schemas.payloads import ActionType

# Attack bounds: a flat to-hit bonus and the max length of a damage dice expression.
ATTACK_BONUS_MIN = -20
ATTACK_BONUS_MAX = 20
DAMAGE_EXPR_MAX_LENGTH = 32
DEFAULT_ATTACK_DAMAGE = "1d6"
# The damage type an attack deals if the client omits one (the generic weapon hit).
DEFAULT_ATTACK_DAMAGE_TYPE = DamageType.SLASHING


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
    damage_type: DamageType = Field(
        default=DEFAULT_ATTACK_DAMAGE_TYPE,
        description="The damage type dealt on a hit (used for the target's resistances).",
    )

    @field_validator("damage")
    @classmethod
    def _check_damage(cls, damage: str) -> str:
        """Reject a malformed / out-of-bounds dice expression at parse time."""
        try:
            parse_dice(damage)
        except DiceExpressionError as exc:
            raise ValueError(str(exc)) from exc
        return damage


class AttackResultPayload(BaseModel):
    """Server → all clients: the resolved outcome of an attack — the log line.

    Built by the server after rolling: the raw d20, the bonus + total, whether it
    hit the target's Armor Class, and (on a hit) the rolled damage breakdown after
    the target's resistance/vulnerability/immunity is applied. This is what everyone
    sees in the shared combat log. It is BROADCAST-only (it never arrives as a client
    intent), so it appears in the broadcast union, not the intent union.

    Rules wiring (Phase 6): the d20 total is compared against the target's AC via
    :func:`app.rules.attack.resolve_attack` (a natural 20 always hits, a natural 1
    always misses); ``advantage`` is derived from the combatants' conditions. Damage
    is rolled and applied ONLY on a hit, and is reduced by the target's ``defense``
    for ``damage_type`` via :func:`app.rules.damage.resolve_damage`. On a miss the
    ``damage_rolls`` are empty and ``damage_total`` is 0.
    """

    type: Literal[ActionType.ATTACK] = ActionType.ATTACK
    attacker_token_id: uuid.UUID = Field(description="Token that made the attack.")
    target_token_id: uuid.UUID = Field(description="Token that was attacked.")
    attack_roll: int = Field(ge=1, le=D20_SIDES, description="The selected d20 result (1..20).")
    attack_bonus: int = Field(description="Flat bonus added to the d20 roll.")
    attack_total: int = Field(description="attack_roll + attack_bonus.")
    advantage: Advantage = Field(description="Whether the roll had advantage/disadvantage.")
    armor_class: int = Field(description="The target's Armor Class the roll was compared against.")
    is_hit: bool = Field(description="Whether the attack hit (total >= AC, or a natural 20).")
    is_critical_hit: bool = Field(description="Whether the d20 was a natural 20.")
    is_critical_miss: bool = Field(description="Whether the d20 was a natural 1.")
    damage: str = Field(description="The damage dice expression that was rolled.")
    damage_type: DamageType = Field(description="The damage type dealt.")
    defense: Defense = Field(description="The target's defense applied to the damage.")
    damage_rolls: list[int] = Field(description="Each damage die result (empty on miss).")
    damage_total: int = Field(ge=0, description="Total damage applied to the target (0 on miss).")
