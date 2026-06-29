"""Pure D&D 2024 attack-roll resolution — part of the isolated rules engine.

CLAUDE.md rule 4: the attack-vs-AC math is pure tabletop logic, so it lives here
with the rest of the rules engine, free of the transport, API and UI layers (the
boundary is enforced by ``tests/test_rules_module.py``). CLAUDE.md rule 1 (server
is authoritative): the SERVER rolls the d20 — the client never supplies it — so
:func:`resolve_attack` takes an injectable :class:`random.Random`, staying
deterministic under test while using a process RNG in production.

The 2024 Player's Handbook attack rules modelled here:

* an **attack roll** is ``d20 + attack_bonus`` compared against the target's
  **Armor Class** (AC); a total **≥ AC hits**, otherwise it misses;
* a natural **20** on the die is a **critical hit** — it hits regardless of AC;
* a natural **1** on the die is an **automatic miss** — it misses regardless of AC;
* **advantage** rolls two d20s and uses the **higher**; **disadvantage** rolls
  two and uses the **lower**; a normal roll uses a single d20.

This module only RESOLVES a roll — wiring it into the Phase-5 attack/damage
actions (deciding where AC lives in the protocol, gating applied damage on a hit)
is the separate "Wire rules engine into the attack/damage actions" task.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from app.rules.dice import D20_SIDES, roll_d20

# The two special faces of the attack die (2024 PHB).
NATURAL_CRIT = D20_SIDES  # a natural 20 always hits (critical hit)
NATURAL_MISS = 1  # a natural 1 always misses

# Armor Class is bounded to a sane tabletop range; AC ~5 (helpless) .. ~30 (the
# toughest creatures) in play, with headroom for buffs.
MIN_ARMOR_CLASS = 1
MAX_ARMOR_CLASS = 50

# A flat to-hit bonus is bounded to mirror the Action schema's attack_bonus range.
MIN_ATTACK_BONUS = -20
MAX_ATTACK_BONUS = 20


class ArmorClassError(ValueError):
    """An Armor Class was outside the allowed 1..50 range."""


class AttackBonusError(ValueError):
    """An attack bonus was outside the allowed -20..20 range."""


class Advantage(StrEnum):
    """Whether an attack roll is made with advantage, disadvantage or neither."""

    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


@dataclass(frozen=True)
class AttackRoll:
    """The resolved outcome of a single attack roll versus an Armor Class.

    ``rolls`` holds every d20 actually rolled (one for a normal roll, two under
    advantage/disadvantage); ``d20`` is the one selected per :attr:`advantage`.
    """

    rolls: tuple[int, ...]
    advantage: Advantage
    d20: int
    attack_bonus: int
    total: int
    armor_class: int
    is_critical_hit: bool
    is_critical_miss: bool
    is_hit: bool


def d20_count(advantage: Advantage) -> int:
    """How many d20s a roll with ``advantage`` rolls: 2 for adv/disadv, else 1."""
    return 2 if advantage is not Advantage.NORMAL else 1


def select_d20(rolls: tuple[int, ...], advantage: Advantage) -> int:
    """Pick the effective d20 from ``rolls`` given ``advantage``.

    Advantage takes the highest die, disadvantage the lowest, a normal roll the
    single die. Raises :class:`ValueError` if no dice were rolled.
    """
    if not rolls:
        raise ValueError("select_d20 needs at least one rolled die.")
    if advantage is Advantage.ADVANTAGE:
        return max(rolls)
    if advantage is Advantage.DISADVANTAGE:
        return min(rolls)
    return rolls[0]


def attack_hits(d20: int, total: int, armor_class: int) -> bool:
    """Whether a roll lands: nat-20 always hits, nat-1 always misses, else total ≥ AC."""
    if d20 == NATURAL_CRIT:
        return True
    if d20 == NATURAL_MISS:
        return False
    return total >= armor_class


def resolve_attack(
    *,
    armor_class: int,
    attack_bonus: int = 0,
    advantage: Advantage = Advantage.NORMAL,
    rng: random.Random,
) -> AttackRoll:
    """Roll a d20 attack (server-authoritative) against ``armor_class`` and resolve it.

    Rolls one d20, or two and selects per ``advantage``; adds the flat
    ``attack_bonus`` to form the total; then decides hit/miss with the 2024 rules
    (natural 20 = critical hit, natural 1 = automatic miss, otherwise total ≥ AC).

    Raises :class:`ArmorClassError` / :class:`AttackBonusError` if the inputs are
    out of range.
    """
    if not MIN_ARMOR_CLASS <= armor_class <= MAX_ARMOR_CLASS:
        raise ArmorClassError(f"armor class must be {MIN_ARMOR_CLASS}..{MAX_ARMOR_CLASS}")
    if not MIN_ATTACK_BONUS <= attack_bonus <= MAX_ATTACK_BONUS:
        raise AttackBonusError(f"attack bonus must be {MIN_ATTACK_BONUS}..{MAX_ATTACK_BONUS}")

    rolls = tuple(roll_d20(rng=rng) for _ in range(d20_count(advantage)))
    d20 = select_d20(rolls, advantage)
    total = d20 + attack_bonus
    return AttackRoll(
        rolls=rolls,
        advantage=advantage,
        d20=d20,
        attack_bonus=attack_bonus,
        total=total,
        armor_class=armor_class,
        is_critical_hit=d20 == NATURAL_CRIT,
        is_critical_miss=d20 == NATURAL_MISS,
        is_hit=attack_hits(d20, total, armor_class),
    )
