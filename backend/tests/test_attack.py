"""Unit tests for the pure attack-roll-vs-AC rules (CLAUDE.md rule 4).

The attack math is deterministic under test because the d20 is rolled through an
injected :class:`random.Random` (seeded) — mirroring the server-authoritative roll.
"""

from __future__ import annotations

import random

import pytest
from app.rules import (
    Advantage,
    ArmorClassError,
    AttackBonusError,
    attack_hits,
    d20_count,
    resolve_attack,
    select_d20,
)


class _ScriptedRandom(random.Random):
    """A Random whose ``randint`` returns a fixed script of d20 results in order."""

    def __init__(self, results: list[int]) -> None:
        super().__init__()
        self._results = list(results)

    def randint(self, a: int, b: int) -> int:
        return self._results.pop(0)


def test_d20_count_is_two_only_with_advantage_or_disadvantage() -> None:
    assert d20_count(Advantage.NORMAL) == 1
    assert d20_count(Advantage.ADVANTAGE) == 2
    assert d20_count(Advantage.DISADVANTAGE) == 2


@pytest.mark.parametrize(
    ("rolls", "advantage", "expected"),
    [
        ((7,), Advantage.NORMAL, 7),
        ((3, 18), Advantage.ADVANTAGE, 18),
        ((3, 18), Advantage.DISADVANTAGE, 3),
        ((15, 15), Advantage.ADVANTAGE, 15),
    ],
)
def test_select_d20_picks_per_advantage(
    rolls: tuple[int, ...], advantage: Advantage, expected: int
) -> None:
    assert select_d20(rolls, advantage) == expected


def test_select_d20_requires_a_die() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_d20((), Advantage.NORMAL)


@pytest.mark.parametrize(
    ("d20", "total", "armor_class", "expected"),
    [
        (10, 15, 15, True),  # meets AC exactly
        (10, 14, 15, False),  # one under AC
        (10, 16, 15, True),  # over AC
        (20, 5, 99, True),  # natural 20 always hits, even vs huge AC
        (1, 99, 1, False),  # natural 1 always misses, even with a huge total
    ],
)
def test_attack_hits_rules(d20: int, total: int, armor_class: int, expected: bool) -> None:
    assert attack_hits(d20, total, armor_class) is expected


def test_resolve_attack_normal_hit_adds_bonus() -> None:
    rng = _ScriptedRandom([14])
    result = resolve_attack(armor_class=15, attack_bonus=5, rng=rng)
    assert result.rolls == (14,)
    assert result.d20 == 14
    assert result.total == 19
    assert result.is_hit is True
    assert result.is_critical_hit is False
    assert result.is_critical_miss is False
    assert result.advantage is Advantage.NORMAL


def test_resolve_attack_miss_below_ac() -> None:
    rng = _ScriptedRandom([8])
    result = resolve_attack(armor_class=18, attack_bonus=2, rng=rng)
    assert result.total == 10
    assert result.is_hit is False


def test_resolve_attack_natural_twenty_is_critical_hit_regardless_of_ac() -> None:
    rng = _ScriptedRandom([20])
    result = resolve_attack(armor_class=50, attack_bonus=-20, rng=rng)
    assert result.is_critical_hit is True
    assert result.is_hit is True


def test_resolve_attack_natural_one_is_automatic_miss() -> None:
    rng = _ScriptedRandom([1])
    result = resolve_attack(armor_class=1, attack_bonus=20, rng=rng)
    assert result.is_critical_miss is True
    assert result.is_hit is False


def test_resolve_attack_advantage_rolls_two_and_takes_higher() -> None:
    rng = _ScriptedRandom([4, 17])
    result = resolve_attack(armor_class=15, attack_bonus=0, advantage=Advantage.ADVANTAGE, rng=rng)
    assert result.rolls == (4, 17)
    assert result.d20 == 17
    assert result.total == 17
    assert result.is_hit is True


def test_resolve_attack_disadvantage_rolls_two_and_takes_lower() -> None:
    rng = _ScriptedRandom([4, 17])
    result = resolve_attack(
        armor_class=15, attack_bonus=0, advantage=Advantage.DISADVANTAGE, rng=rng
    )
    assert result.rolls == (4, 17)
    assert result.d20 == 4
    assert result.is_hit is False


@pytest.mark.parametrize("armor_class", [0, 51, -1])
def test_resolve_attack_rejects_out_of_range_armor_class(armor_class: int) -> None:
    with pytest.raises(ArmorClassError):
        resolve_attack(armor_class=armor_class, rng=random.Random(0))


@pytest.mark.parametrize("attack_bonus", [-21, 21])
def test_resolve_attack_rejects_out_of_range_attack_bonus(attack_bonus: int) -> None:
    with pytest.raises(AttackBonusError):
        resolve_attack(armor_class=15, attack_bonus=attack_bonus, rng=random.Random(0))


def test_resolve_attack_is_deterministic_for_a_given_seed() -> None:
    a = resolve_attack(armor_class=15, attack_bonus=3, rng=random.Random(42))
    b = resolve_attack(armor_class=15, attack_bonus=3, rng=random.Random(42))
    assert a == b
