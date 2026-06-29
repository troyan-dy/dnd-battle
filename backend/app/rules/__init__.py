"""Isolated D&D 2024 rules engine (CLAUDE.md rule 4).

Pure, fully-unit-tested rules/dice math, kept free of the transport and UI layers.
This package is the seed of the Phase-6 rules engine; the Phase-5 attack flow
composes :mod:`app.rules.dice` for its server-authoritative rolls.

Boundary contract (enforced mechanically by ``tests/test_rules_module.py``):

* every module under this package is **pure** — it imports only the standard
  library and its sibling rules modules, never the transport (``app.realtime``),
  API (``app.api``), persistence (``app.db`` / ``app.models``), service,
  schema, storage or security layers, nor their frameworks (FastAPI, Socket.IO,
  SQLAlchemy, Pydantic). Outer layers depend on the rules engine, never the
  reverse;
* server-authoritative randomness (CLAUDE.md rule 1) is injected as a
  :class:`random.Random`, so the whole engine is deterministic under test.

Import the engine's public surface from this package (``from app.rules import
roll_dice``) rather than reaching into submodules — ``__all__`` is the supported
contract that later Phase-6 tasks (ability scores, attack-vs-AC, damage types,
conditions) extend.
"""

from __future__ import annotations

from app.rules.abilities import (
    MAX_ABILITY_SCORE,
    MAX_LEVEL,
    MAX_PROFICIENCY_BONUS,
    MIN_ABILITY_SCORE,
    MIN_LEVEL,
    MIN_PROFICIENCY_BONUS,
    Ability,
    AbilityModifier,
    AbilityScoreError,
    LevelError,
    ability_modifier,
    format_modifier,
    proficiency_bonus,
)
from app.rules.attack import (
    MAX_ARMOR_CLASS,
    MAX_ATTACK_BONUS,
    MIN_ARMOR_CLASS,
    MIN_ATTACK_BONUS,
    NATURAL_CRIT,
    NATURAL_MISS,
    Advantage,
    ArmorClassError,
    AttackBonusError,
    AttackRoll,
    attack_hits,
    d20_count,
    resolve_attack,
    select_d20,
)
from app.rules.conditions import (
    CONDITION_EFFECTS,
    Condition,
    ConditionEffect,
    condition_effect,
    incoming_attack_advantage,
    outgoing_attack_advantage,
)
from app.rules.damage import (
    DamageResult,
    DamageType,
    Defense,
    apply_defense,
    resolve_damage,
)
from app.rules.dice import (
    D20_SIDES,
    MAX_DICE_COUNT,
    MAX_DICE_SIDES,
    MAX_FLAT_AMOUNT,
    MAX_MODIFIER,
    DiceExpressionError,
    DiceRoll,
    ParsedDice,
    parse_dice,
    roll_d20,
    roll_dice,
    roll_die,
)

__all__ = [
    "CONDITION_EFFECTS",
    "D20_SIDES",
    "MAX_ABILITY_SCORE",
    "MAX_ARMOR_CLASS",
    "MAX_ATTACK_BONUS",
    "MAX_DICE_COUNT",
    "MAX_DICE_SIDES",
    "MAX_FLAT_AMOUNT",
    "MAX_LEVEL",
    "MAX_MODIFIER",
    "MAX_PROFICIENCY_BONUS",
    "MIN_ABILITY_SCORE",
    "MIN_ARMOR_CLASS",
    "MIN_ATTACK_BONUS",
    "MIN_LEVEL",
    "MIN_PROFICIENCY_BONUS",
    "NATURAL_CRIT",
    "NATURAL_MISS",
    "Ability",
    "AbilityModifier",
    "AbilityScoreError",
    "Advantage",
    "ArmorClassError",
    "AttackBonusError",
    "AttackRoll",
    "Condition",
    "ConditionEffect",
    "DamageResult",
    "DamageType",
    "Defense",
    "DiceExpressionError",
    "DiceRoll",
    "LevelError",
    "ParsedDice",
    "ability_modifier",
    "apply_defense",
    "attack_hits",
    "condition_effect",
    "d20_count",
    "format_modifier",
    "incoming_attack_advantage",
    "outgoing_attack_advantage",
    "parse_dice",
    "proficiency_bonus",
    "resolve_attack",
    "resolve_damage",
    "roll_d20",
    "roll_dice",
    "roll_die",
    "select_d20",
]
