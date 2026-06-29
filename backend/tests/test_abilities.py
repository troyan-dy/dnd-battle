"""Unit tests for the pure D&D 2024 ability-score math (app.rules.abilities)."""

from __future__ import annotations

import pytest
from app.rules import (
    MAX_ABILITY_SCORE,
    MAX_LEVEL,
    MIN_ABILITY_SCORE,
    MIN_LEVEL,
    Ability,
    AbilityModifier,
    AbilityScoreError,
    LevelError,
    ability_modifier,
    format_modifier,
    proficiency_bonus,
)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1, -5),  # floor((1 - 10) / 2) = -5 (odd low score rounds toward -inf)
        (3, -4),
        (8, -1),
        (9, -1),  # odd score shares the lower even score's modifier
        (10, 0),
        (11, 0),
        (12, 1),
        (15, 2),
        (18, 4),
        (20, 5),
        (30, 10),
    ],
)
def test_ability_modifier_formula(score: int, expected: int) -> None:
    assert ability_modifier(score) == expected


@pytest.mark.parametrize("score", [0, -1, 31, 100, MIN_ABILITY_SCORE - 1, MAX_ABILITY_SCORE + 1])
def test_ability_modifier_rejects_out_of_range(score: int) -> None:
    with pytest.raises(AbilityScoreError):
        ability_modifier(score)


@pytest.mark.parametrize(
    ("modifier", "expected"),
    [(0, "+0"), (3, "+3"), (-1, "-1"), (5, "+5"), (-5, "-5")],
)
def test_format_modifier_signed(modifier: int, expected: str) -> None:
    assert format_modifier(modifier) == expected


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (1, 2),
        (4, 2),
        (5, 3),
        (8, 3),
        (9, 4),
        (12, 4),
        (13, 5),
        (16, 5),
        (17, 6),
        (20, 6),
    ],
)
def test_proficiency_bonus_by_level(level: int, expected: int) -> None:
    assert proficiency_bonus(level) == expected


@pytest.mark.parametrize("level", [0, -1, 21, MIN_LEVEL - 1, MAX_LEVEL + 1])
def test_proficiency_bonus_rejects_out_of_range(level: int) -> None:
    with pytest.raises(LevelError):
        proficiency_bonus(level)


def test_proficiency_bonus_is_monotonic_non_decreasing() -> None:
    bonuses = [proficiency_bonus(level) for level in range(MIN_LEVEL, MAX_LEVEL + 1)]
    assert bonuses == sorted(bonuses)
    assert bonuses[0] == 2
    assert bonuses[-1] == 6


def test_ability_enum_codes() -> None:
    assert [a.value for a in Ability] == ["str", "dex", "con", "int", "wis", "cha"]
    assert Ability("dex") is Ability.DEXTERITY


def test_ability_modifier_dataclass_signed_property() -> None:
    score = 17
    am = AbilityModifier(score=score, modifier=ability_modifier(score))
    assert am.score == 17
    assert am.modifier == 3
    assert am.signed == "+3"

    negative = AbilityModifier(score=8, modifier=ability_modifier(8))
    assert negative.signed == "-1"
