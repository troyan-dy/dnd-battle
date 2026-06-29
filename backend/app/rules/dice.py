"""Pure dice-rolling primitives — the seed of the Phase-6 D&D 2024 rules engine.

CLAUDE.md rule 4: rules / dice math lives in its own module of pure functions with
unit tests, isolated from the transport and UI layers. CLAUDE.md rule 1 (server is
authoritative): the SERVER rolls the dice — clients never supply roll results — so
these helpers take an injectable :class:`random.Random` to stay deterministic under
test while using a process RNG in production.

A *dice expression* is the familiar ``NdS(+/-M)`` tabletop shorthand:

* ``"1d20"``  -> roll one twenty-sided die,
* ``"2d6+3"`` -> roll two six-sided dice and add 3,
* ``"d8"``    -> the count defaults to 1,
* ``"4"``     -> a flat amount (no dice).

Counts / sides / modifiers are bounded so a single expression can never request an
absurd number of rolls (and the Action schema reuses :func:`parse_dice` to reject a
malformed expression at parse time, before any roll happens).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# A twenty-sided die — the basis of every attack/check/save roll in D&D 2024.
D20_SIDES = 20

# Bounds keeping a single expression sane (and the server cheap to evaluate).
MAX_DICE_COUNT = 50
MAX_DICE_SIDES = 1000
MAX_MODIFIER = 1000
MAX_FLAT_AMOUNT = 1000

# `NdS`, `NdS+M`, `NdS-M` (count optional, case-insensitive d) and a flat integer.
_DICE_RE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$", re.IGNORECASE)
_FLAT_RE = re.compile(r"^([+-]?\d+)$")


class DiceExpressionError(ValueError):
    """A dice expression was malformed or out of the allowed bounds."""


@dataclass(frozen=True)
class ParsedDice:
    """A validated dice expression: ``count`` dice of ``sides`` plus a ``modifier``.

    A flat amount (e.g. ``"4"``) parses as ``count=0, sides=0`` with the value in
    ``modifier`` — there are no dice to roll, just a constant.
    """

    count: int
    sides: int
    modifier: int


@dataclass(frozen=True)
class DiceRoll:
    """The outcome of rolling a :class:`ParsedDice`: each die result + the total."""

    rolls: tuple[int, ...]
    modifier: int
    total: int


def parse_dice(expression: str) -> ParsedDice:
    """Parse + bounds-check a dice expression. Raises :class:`DiceExpressionError`."""
    text = expression.strip().replace(" ", "")
    if not text:
        raise DiceExpressionError("Empty dice expression.")

    flat = _FLAT_RE.match(text)
    if flat is not None:
        value = int(flat.group(1))
        if abs(value) > MAX_FLAT_AMOUNT:
            raise DiceExpressionError("Flat amount out of range.")
        return ParsedDice(count=0, sides=0, modifier=value)

    match = _DICE_RE.match(text)
    if match is None:
        raise DiceExpressionError(f"Invalid dice expression: {expression!r}.")

    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    if not 1 <= count <= MAX_DICE_COUNT:
        raise DiceExpressionError("Dice count out of range.")
    if not 1 <= sides <= MAX_DICE_SIDES:
        raise DiceExpressionError("Dice sides out of range.")
    if abs(modifier) > MAX_MODIFIER:
        raise DiceExpressionError("Modifier out of range.")
    return ParsedDice(count=count, sides=sides, modifier=modifier)


def roll_die(sides: int, *, rng: random.Random) -> int:
    """Roll a single ``sides``-sided die using ``rng`` (result in ``1..sides``)."""
    if sides < 1:
        raise DiceExpressionError("A die must have at least one side.")
    return rng.randint(1, sides)


def roll_d20(*, rng: random.Random) -> int:
    """Roll a single d20 (the D&D attack/check/save die)."""
    return roll_die(D20_SIDES, rng=rng)


def roll_dice(expression: str, *, rng: random.Random) -> DiceRoll:
    """Parse + roll a dice expression, returning each die result and the total."""
    parsed = parse_dice(expression)
    rolls = (
        tuple(roll_die(parsed.sides, rng=rng) for _ in range(parsed.count)) if parsed.sides else ()
    )
    total = sum(rolls) + parsed.modifier
    return DiceRoll(rolls=rolls, modifier=parsed.modifier, total=total)
