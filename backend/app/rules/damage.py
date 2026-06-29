"""Pure D&D 2024 damage resolution — part of the isolated rules engine.

CLAUDE.md rule 4: rolling damage, classifying it by type and applying a target's
resistance / vulnerability / immunity are pure tabletop math, so they live here
with the rest of the rules engine, free of the transport, API and UI layers (the
boundary is enforced by ``tests/test_rules_module.py``). CLAUDE.md rule 1 (server
is authoritative): the SERVER rolls the damage dice — the client never supplies a
result — so :func:`resolve_damage` takes an injectable :class:`random.Random`,
staying deterministic under test while using a process RNG in production.

The 2024 Player's Handbook damage rules modelled here:

* damage is rolled from a dice expression (``"2d6+3"`` etc., parsed + bounded by
  :mod:`app.rules.dice`) and carries one of the thirteen **damage types**;
* a target may have a **defense** against that type — **resistance** halves the
  damage (rounded down), **vulnerability** doubles it, **immunity** reduces it to
  zero, and a **normal** relationship leaves it unchanged;
* the final amount never drops below zero.

This module only RESOLVES damage — wiring it (and where a creature's
resistances live in the protocol) into the Phase-5 attack/damage actions is the
separate "Wire rules engine into the attack/damage actions" task.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from app.rules.dice import DiceRoll, roll_dice


class DamageType(StrEnum):
    """The thirteen D&D 2024 damage types."""

    ACID = "acid"
    BLUDGEONING = "bludgeoning"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    PIERCING = "piercing"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    SLASHING = "slashing"
    THUNDER = "thunder"


class Defense(StrEnum):
    """How a target relates to an incoming damage type (2024 PHB)."""

    NORMAL = "normal"
    RESISTANCE = "resistance"
    VULNERABILITY = "vulnerability"
    IMMUNITY = "immunity"


@dataclass(frozen=True)
class DamageResult:
    """The resolved outcome of rolling + defending a packet of typed damage.

    ``raw_total`` is the rolled total before any defense is applied; ``total`` is
    the final amount the target takes after resistance / vulnerability / immunity.
    """

    rolls: tuple[int, ...]
    modifier: int
    damage_type: DamageType
    defense: Defense
    raw_total: int
    total: int


def apply_defense(amount: int, defense: Defense) -> int:
    """Apply a ``defense`` to a non-negative damage ``amount`` (2024 PHB).

    Immunity → 0, resistance → halved (rounded down), vulnerability → doubled,
    normal → unchanged. The result is never below zero.
    """
    base = max(amount, 0)
    if defense is Defense.IMMUNITY:
        return 0
    if defense is Defense.RESISTANCE:
        return base // 2
    if defense is Defense.VULNERABILITY:
        return base * 2
    return base


def resolve_damage(
    *,
    expression: str,
    damage_type: DamageType,
    defense: Defense = Defense.NORMAL,
    rng: random.Random,
) -> DamageResult:
    """Roll a damage ``expression`` (server-authoritative) and apply ``defense``.

    Rolls the dice via :func:`app.rules.dice.roll_dice`, classifies the result as
    ``damage_type``, then applies the target's ``defense`` to the raw total to get
    the final amount taken (clamped at zero).

    Raises :class:`app.rules.dice.DiceExpressionError` if the expression is
    malformed or out of range.
    """
    roll: DiceRoll = roll_dice(expression, rng=rng)
    raw_total = max(roll.total, 0)
    total = apply_defense(raw_total, defense)
    return DamageResult(
        rolls=roll.rolls,
        modifier=roll.modifier,
        damage_type=damage_type,
        defense=defense,
        raw_total=raw_total,
        total=total,
    )
