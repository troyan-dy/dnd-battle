"""Pure D&D 2024 ability-score math — part of the isolated rules engine.

CLAUDE.md rule 4: ability scores, their modifiers and the proficiency bonus are
pure tabletop math, so they live here with the rest of the rules engine rather
than in the transport, API or UI layers. Outer layers depend on this module; it
imports only the standard library (enforced by ``tests/test_rules_module.py``).

The two core formulas of the 2024 Player's Handbook:

* an **ability modifier** is ``floor((score - 10) / 2)`` (the frontend mirrors
  this in ``frontend/src/screens/abilityModifier.ts`` for display), and
* the **proficiency bonus** grows with character level: ``+2`` at levels 1-4,
  rising by one every four levels up to ``+6`` at levels 17-20 — i.e.
  ``2 + (level - 1) // 4``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# D&D 2024 ability-score range (1 = drained to nothing, 30 = a deity's might).
# Matches the AbilityScores Pydantic bounds in app/schemas/room.py.
MIN_ABILITY_SCORE = 1
MAX_ABILITY_SCORE = 30

# Character levels run 1..20 in the 2024 ruleset.
MIN_LEVEL = 1
MAX_LEVEL = 20

# Proficiency bonus is +2 at level 1 and +6 at level 20.
MIN_PROFICIENCY_BONUS = 2
MAX_PROFICIENCY_BONUS = 6


class AbilityScoreError(ValueError):
    """An ability score was outside the allowed 1..30 range."""


class LevelError(ValueError):
    """A character level was outside the allowed 1..20 range."""


class Ability(StrEnum):
    """The six D&D 2024 abilities, keyed by their canonical three-letter codes."""

    STRENGTH = "str"
    DEXTERITY = "dex"
    CONSTITUTION = "con"
    INTELLIGENCE = "int"
    WISDOM = "wis"
    CHARISMA = "cha"


@dataclass(frozen=True)
class AbilityModifier:
    """An ability score paired with its derived modifier."""

    score: int
    modifier: int

    @property
    def signed(self) -> str:
        """The modifier formatted with an explicit sign, e.g. ``"+3"`` or ``"-1"``."""
        return format_modifier(self.modifier)


def ability_modifier(score: int) -> int:
    """``floor((score - 10) / 2)`` for a valid 1..30 ability score.

    Raises :class:`AbilityScoreError` if ``score`` is out of range.
    """
    if not MIN_ABILITY_SCORE <= score <= MAX_ABILITY_SCORE:
        raise AbilityScoreError(f"ability score must be {MIN_ABILITY_SCORE}..{MAX_ABILITY_SCORE}")
    # Python's floor division already rounds toward negative infinity, matching
    # floor((score - 10) / 2) for every score in range (incl. odd low scores).
    return (score - 10) // 2


def format_modifier(modifier: int) -> str:
    """Format a modifier with an explicit sign (mirrors the frontend helper)."""
    return f"+{modifier}" if modifier >= 0 else str(modifier)


def proficiency_bonus(level: int) -> int:
    """The proficiency bonus for a character ``level`` (1..20): ``2 + (level-1)//4``.

    Raises :class:`LevelError` if ``level`` is out of range.
    """
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise LevelError(f"level must be {MIN_LEVEL}..{MAX_LEVEL}")
    return MIN_PROFICIENCY_BONUS + (level - 1) // 4
