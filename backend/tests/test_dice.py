"""Unit tests for the pure dice primitives (app/rules/dice.py).

The roll math is isolated from transport/UI (CLAUDE.md rule 4) and takes an
injectable RNG, so these tests are fully deterministic.
"""

from __future__ import annotations

import random

import pytest
from app.rules.dice import (
    D20_SIDES,
    MAX_DICE_COUNT,
    MAX_DICE_SIDES,
    DiceExpressionError,
    parse_dice,
    roll_d20,
    roll_dice,
    roll_die,
)


def test_parse_simple_dice() -> None:
    parsed = parse_dice("2d6+3")
    assert (parsed.count, parsed.sides, parsed.modifier) == (2, 6, 3)


def test_parse_defaults_count_to_one() -> None:
    parsed = parse_dice("d8")
    assert (parsed.count, parsed.sides, parsed.modifier) == (1, 8, 0)


def test_parse_negative_modifier_and_whitespace() -> None:
    parsed = parse_dice("  1d20 - 2 ")
    assert (parsed.count, parsed.sides, parsed.modifier) == (1, 20, -2)


def test_parse_flat_amount() -> None:
    parsed = parse_dice("5")
    assert (parsed.count, parsed.sides, parsed.modifier) == (0, 0, 5)


@pytest.mark.parametrize(
    "expr",
    ["", "abc", "d", "2x6", "0d6", f"{MAX_DICE_COUNT + 1}d6", f"1d{MAX_DICE_SIDES + 1}"],
)
def test_parse_rejects_bad_expressions(expr: str) -> None:
    with pytest.raises(DiceExpressionError):
        parse_dice(expr)


def test_roll_die_is_within_range() -> None:
    rng = random.Random(123)
    for _ in range(200):
        assert 1 <= roll_die(6, rng=rng) <= 6


def test_roll_die_rejects_non_positive_sides() -> None:
    with pytest.raises(DiceExpressionError):
        roll_die(0, rng=random.Random(0))


def test_roll_d20_uses_twenty_sides() -> None:
    rng = random.Random(7)
    for _ in range(200):
        assert 1 <= roll_d20(rng=rng) <= D20_SIDES


def test_roll_dice_is_deterministic_for_a_seed() -> None:
    a = roll_dice("3d6+1", rng=random.Random(42))
    b = roll_dice("3d6+1", rng=random.Random(42))
    assert a == b
    assert len(a.rolls) == 3
    assert a.total == sum(a.rolls) + 1
    assert all(1 <= r <= 6 for r in a.rolls)


def test_roll_dice_flat_amount_has_no_rolls() -> None:
    result = roll_dice("4", rng=random.Random(0))
    assert result.rolls == ()
    assert result.total == 4
