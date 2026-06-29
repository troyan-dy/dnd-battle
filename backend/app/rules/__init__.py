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
    "D20_SIDES",
    "MAX_DICE_COUNT",
    "MAX_DICE_SIDES",
    "MAX_FLAT_AMOUNT",
    "MAX_MODIFIER",
    "DiceExpressionError",
    "DiceRoll",
    "ParsedDice",
    "parse_dice",
    "roll_d20",
    "roll_dice",
    "roll_die",
]
