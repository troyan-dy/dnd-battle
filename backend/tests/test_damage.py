"""Unit tests for the pure damage rules: rolls, types and basic resistances.

The damage math is deterministic under test because the dice are rolled through an
injected :class:`random.Random` (seeded / scripted) — mirroring the
server-authoritative roll (CLAUDE.md rules 1 & 4).
"""

from __future__ import annotations

import random

import pytest
from app.rules import (
    DamageResult,
    DamageType,
    Defense,
    apply_defense,
    resolve_damage,
)
from app.rules.dice import DiceExpressionError

from tests.support import ScriptedRandom


def test_damage_types_cover_the_thirteen_2024_types() -> None:
    assert {damage_type.value for damage_type in DamageType} == {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }


def test_defense_members() -> None:
    assert {defense.value for defense in Defense} == {
        "normal",
        "resistance",
        "vulnerability",
        "immunity",
    }


@pytest.mark.parametrize(
    ("amount", "defense", "expected"),
    [
        (10, Defense.NORMAL, 10),
        (10, Defense.RESISTANCE, 5),
        (10, Defense.VULNERABILITY, 20),
        (10, Defense.IMMUNITY, 0),
        # Resistance rounds down (PHB): 7 // 2 == 3.
        (7, Defense.RESISTANCE, 3),
        (1, Defense.RESISTANCE, 0),
        (0, Defense.VULNERABILITY, 0),
        # Defensive clamp: a negative amount never yields negative damage.
        (-5, Defense.NORMAL, 0),
        (-5, Defense.VULNERABILITY, 0),
        (-5, Defense.RESISTANCE, 0),
    ],
)
def test_apply_defense_multipliers(amount: int, defense: Defense, expected: int) -> None:
    assert apply_defense(amount, defense) == expected


def test_resolve_damage_normal_rolls_and_classifies() -> None:
    rng = ScriptedRandom([4, 5])
    outcome = resolve_damage(expression="2d6+3", damage_type=DamageType.FIRE, rng=rng)
    assert isinstance(outcome, DamageResult)
    assert outcome.rolls == (4, 5)
    assert outcome.modifier == 3
    assert outcome.damage_type is DamageType.FIRE
    assert outcome.defense is Defense.NORMAL
    assert outcome.raw_total == 12
    assert outcome.total == 12


def test_resolve_damage_resistance_halves_rounding_down() -> None:
    rng = ScriptedRandom([4, 5])  # 2d6+3 -> 12, resisted -> 6
    outcome = resolve_damage(
        expression="2d6+3",
        damage_type=DamageType.COLD,
        defense=Defense.RESISTANCE,
        rng=rng,
    )
    assert outcome.raw_total == 12
    assert outcome.total == 6


def test_resolve_damage_resistance_rounds_down_on_odd_total() -> None:
    rng = ScriptedRandom([5])  # 1d6+2 -> 7, resisted -> 3 (round down)
    outcome = resolve_damage(
        expression="1d6+2",
        damage_type=DamageType.SLASHING,
        defense=Defense.RESISTANCE,
        rng=rng,
    )
    assert outcome.raw_total == 7
    assert outcome.total == 3


def test_resolve_damage_vulnerability_doubles() -> None:
    rng = ScriptedRandom([4, 5])  # 12 -> 24
    outcome = resolve_damage(
        expression="2d6+3",
        damage_type=DamageType.NECROTIC,
        defense=Defense.VULNERABILITY,
        rng=rng,
    )
    assert outcome.total == 24


def test_resolve_damage_immunity_zeroes() -> None:
    rng = ScriptedRandom([6, 6])
    outcome = resolve_damage(
        expression="2d6+3",
        damage_type=DamageType.POISON,
        defense=Defense.IMMUNITY,
        rng=rng,
    )
    assert outcome.raw_total == 15
    assert outcome.total == 0


def test_resolve_damage_flat_expression_has_no_rolls() -> None:
    rng = ScriptedRandom([])
    outcome = resolve_damage(expression="4", damage_type=DamageType.FORCE, rng=rng)
    assert outcome.rolls == ()
    assert outcome.modifier == 4
    assert outcome.raw_total == 4
    assert outcome.total == 4


def test_resolve_damage_rejects_malformed_expression() -> None:
    with pytest.raises(DiceExpressionError):
        resolve_damage(expression="not-dice", damage_type=DamageType.ACID, rng=random.Random(1))


def test_resolve_damage_is_deterministic_under_same_seed() -> None:
    first = resolve_damage(
        expression="3d8+2", damage_type=DamageType.RADIANT, rng=random.Random(99)
    )
    second = resolve_damage(
        expression="3d8+2", damage_type=DamageType.RADIANT, rng=random.Random(99)
    )
    assert first == second
