"""Pure D&D 2024 conditions and their mechanical effects — part of the rules engine.

CLAUDE.md rule 4: the conditions and what they do mechanically (advantage on
attacks against a creature, auto-failed saves, a zeroed Speed, etc.) are pure
tabletop rules, so they live here with the rest of the rules engine, free of the
transport, API and UI layers (the boundary is enforced by
``tests/test_rules_module.py``). Outer layers depend on this module; it imports
only the standard library and its sibling rules modules.

This module models the fifteen conditions of the 2024 Player's Handbook. Each
condition is described by a :class:`ConditionEffect` carrying:

* **unconditional** boolean flags for the effects a rules engine can apply
  directly — whether the creature is Incapacitated, has a Speed of 0, grants
  Advantage / Disadvantage to attacks made against it, has Advantage /
  Disadvantage on its own attacks, has Disadvantage on ability checks,
  automatically fails Strength / Dexterity saving throws, and whether a melee
  hit against it is a Critical Hit; and
* the authoritative 2024 rules text as a tuple of ``effects`` bullets, which also
  captures the *conditional* nuances that can't be a single boolean (e.g. Prone's
  "Advantage if the attacker is within 5 feet, otherwise Disadvantage", or
  Charmed's restriction on attacking the charmer).

Aggregate helpers (:func:`incoming_attack_advantage`,
:func:`outgoing_attack_advantage`) compose a creature's set of conditions into a
single :class:`app.rules.attack.Advantage`, applying the 2024 rule that any
Advantage combined with any Disadvantage cancels to a normal roll.

Wiring these effects into the Phase-5 attack/damage actions is the separate
"Wire rules engine into the attack/damage actions" task; this module only
*describes* the conditions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from app.rules.attack import Advantage


class Condition(StrEnum):
    """The fifteen D&D 2024 conditions."""

    BLINDED = "blinded"
    CHARMED = "charmed"
    DEAFENED = "deafened"
    EXHAUSTION = "exhaustion"
    FRIGHTENED = "frightened"
    GRAPPLED = "grappled"
    INCAPACITATED = "incapacitated"
    INVISIBLE = "invisible"
    PARALYZED = "paralyzed"
    PETRIFIED = "petrified"
    POISONED = "poisoned"
    PRONE = "prone"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    UNCONSCIOUS = "unconscious"


@dataclass(frozen=True)
class ConditionEffect:
    """The mechanical effects of a single condition (2024 PHB).

    The boolean fields describe **unconditional** effects a rules engine can apply
    directly; conditional nuances live in the authoritative ``effects`` text.
    """

    condition: Condition
    # Can't take actions, Bonus Actions, or Reactions.
    incapacitated: bool = False
    # The creature's Speed is 0 (it can't move).
    speed_zero: bool = False
    # Attack rolls against the creature have Advantage / Disadvantage.
    attacks_against_have_advantage: bool = False
    attacks_against_have_disadvantage: bool = False
    # The creature's own attack rolls have Advantage / Disadvantage.
    own_attacks_have_advantage: bool = False
    own_attacks_have_disadvantage: bool = False
    # The creature has Disadvantage on ability checks.
    ability_checks_have_disadvantage: bool = False
    # The creature automatically fails these saving throws.
    auto_fails_strength_saves: bool = False
    auto_fails_dexterity_saves: bool = False
    # A hit by an attacker within 5 feet is a Critical Hit.
    melee_attacks_against_are_critical: bool = False
    # The authoritative 2024 rules text, including any conditional nuances.
    effects: tuple[str, ...] = field(default_factory=tuple)


CONDITION_EFFECTS: dict[Condition, ConditionEffect] = {
    Condition.BLINDED: ConditionEffect(
        condition=Condition.BLINDED,
        attacks_against_have_advantage=True,
        own_attacks_have_disadvantage=True,
        effects=(
            "Can't see and automatically fails any ability check that requires sight.",
            "Attack rolls against the creature have Advantage.",
            "The creature's attack rolls have Disadvantage.",
        ),
    ),
    Condition.CHARMED: ConditionEffect(
        condition=Condition.CHARMED,
        effects=(
            "Can't attack the charmer or target the charmer with harmful abilities "
            "or magical effects.",
            "The charmer has Advantage on any ability check to interact socially with "
            "the creature.",
        ),
    ),
    Condition.DEAFENED: ConditionEffect(
        condition=Condition.DEAFENED,
        effects=("Can't hear and automatically fails any ability check that requires hearing.",),
    ),
    Condition.EXHAUSTION: ConditionEffect(
        condition=Condition.EXHAUSTION,
        effects=(
            "Exhaustion is measured in six levels and its effects are cumulative.",
            "The creature takes a penalty to all D20 Tests equal to 2 times its Exhaustion level.",
            "The creature's Speed is reduced by a number of feet equal to 5 times its "
            "Exhaustion level.",
            "Level 6 Exhaustion is fatal.",
        ),
    ),
    Condition.FRIGHTENED: ConditionEffect(
        condition=Condition.FRIGHTENED,
        own_attacks_have_disadvantage=True,
        ability_checks_have_disadvantage=True,
        effects=(
            "While the source of its fear is within line of sight, the creature has "
            "Disadvantage on ability checks and attack rolls.",
            "The creature can't willingly move closer to the source of its fear.",
        ),
    ),
    Condition.GRAPPLED: ConditionEffect(
        condition=Condition.GRAPPLED,
        speed_zero=True,
        effects=(
            "The creature's Speed is 0 and can't increase.",
            "The creature has Disadvantage on attack rolls against any target other "
            "than the grappler.",
            "The condition ends if the grappler is Incapacitated or if the creature is "
            "moved outside the grappler's reach.",
        ),
    ),
    Condition.INCAPACITATED: ConditionEffect(
        condition=Condition.INCAPACITATED,
        incapacitated=True,
        effects=(
            "The creature can't take any action, Bonus Action, or Reaction.",
            "The creature can't concentrate and can't speak.",
            "If Incapacitated when it rolls Initiative, the creature has Disadvantage on the roll.",
        ),
    ),
    Condition.INVISIBLE: ConditionEffect(
        condition=Condition.INVISIBLE,
        attacks_against_have_disadvantage=True,
        own_attacks_have_advantage=True,
        effects=(
            "The creature isn't affected by any effect that requires its target to be "
            "seen, unless the effect's creator can somehow see it.",
            "The creature is Heavily Obscured for the purpose of hiding.",
            "Attack rolls against the creature have Disadvantage.",
            "The creature's attack rolls have Advantage.",
        ),
    ),
    Condition.PARALYZED: ConditionEffect(
        condition=Condition.PARALYZED,
        incapacitated=True,
        speed_zero=True,
        attacks_against_have_advantage=True,
        auto_fails_strength_saves=True,
        auto_fails_dexterity_saves=True,
        melee_attacks_against_are_critical=True,
        effects=(
            "The creature has the Incapacitated condition and can't move or speak.",
            "The creature automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against the creature have Advantage.",
            "Any attack roll that hits the creature is a Critical Hit if the attacker "
            "is within 5 feet.",
        ),
    ),
    Condition.PETRIFIED: ConditionEffect(
        condition=Condition.PETRIFIED,
        incapacitated=True,
        speed_zero=True,
        attacks_against_have_advantage=True,
        auto_fails_strength_saves=True,
        auto_fails_dexterity_saves=True,
        effects=(
            "The creature is transformed, along with any nonmagical objects it is "
            "wearing and carrying, into a solid inanimate substance; its weight "
            "increases by a factor of ten and it stops aging.",
            "The creature has the Incapacitated condition and can't move or speak.",
            "Attack rolls against the creature have Advantage.",
            "The creature automatically fails Strength and Dexterity saving throws.",
            "The creature has Resistance to all damage.",
            "The creature has Immunity to the Poisoned condition.",
        ),
    ),
    Condition.POISONED: ConditionEffect(
        condition=Condition.POISONED,
        own_attacks_have_disadvantage=True,
        ability_checks_have_disadvantage=True,
        effects=("The creature has Disadvantage on attack rolls and ability checks.",),
    ),
    Condition.PRONE: ConditionEffect(
        condition=Condition.PRONE,
        own_attacks_have_disadvantage=True,
        effects=(
            "The creature's only movement options are to crawl or to spend movement to "
            "stand up, ending the condition.",
            "The creature has Disadvantage on attack rolls.",
            "An attack roll against the creature has Advantage if the attacker is "
            "within 5 feet; otherwise, the attack roll has Disadvantage.",
        ),
    ),
    Condition.RESTRAINED: ConditionEffect(
        condition=Condition.RESTRAINED,
        speed_zero=True,
        attacks_against_have_advantage=True,
        own_attacks_have_disadvantage=True,
        effects=(
            "The creature's Speed is 0 and can't increase.",
            "Attack rolls against the creature have Advantage, and the creature's "
            "attack rolls have Disadvantage.",
            "The creature has Disadvantage on Dexterity saving throws.",
        ),
    ),
    Condition.STUNNED: ConditionEffect(
        condition=Condition.STUNNED,
        incapacitated=True,
        speed_zero=True,
        attacks_against_have_advantage=True,
        auto_fails_strength_saves=True,
        auto_fails_dexterity_saves=True,
        effects=(
            "The creature has the Incapacitated condition and can't move; it can speak "
            "only falteringly.",
            "The creature automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against the creature have Advantage.",
        ),
    ),
    Condition.UNCONSCIOUS: ConditionEffect(
        condition=Condition.UNCONSCIOUS,
        incapacitated=True,
        speed_zero=True,
        attacks_against_have_advantage=True,
        auto_fails_strength_saves=True,
        auto_fails_dexterity_saves=True,
        melee_attacks_against_are_critical=True,
        effects=(
            "The creature has the Incapacitated condition, can't move or speak, and is "
            "unaware of its surroundings.",
            "The creature drops whatever it is holding and falls Prone.",
            "The creature automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against the creature have Advantage.",
            "Any attack roll that hits the creature is a Critical Hit if the attacker "
            "is within 5 feet.",
        ),
    ),
}


def condition_effect(condition: Condition) -> ConditionEffect:
    """Return the :class:`ConditionEffect` describing ``condition``."""
    return CONDITION_EFFECTS[condition]


def _combine_advantage(has_advantage: bool, has_disadvantage: bool) -> Advantage:
    """Combine advantage/disadvantage sources per the 2024 cancellation rule.

    Any number of Advantage sources plus any number of Disadvantage sources cancel
    out to a normal roll; otherwise the present side wins.
    """
    if has_advantage == has_disadvantage:
        return Advantage.NORMAL
    return Advantage.ADVANTAGE if has_advantage else Advantage.DISADVANTAGE


def incoming_attack_advantage(conditions: Iterable[Condition]) -> Advantage:
    """The net Advantage state for an attack made **against** a creature.

    Combines every condition's effect on attacks against the creature; mixed
    Advantage and Disadvantage cancel to :attr:`Advantage.NORMAL`.
    """
    effects = [CONDITION_EFFECTS[c] for c in conditions]
    return _combine_advantage(
        any(e.attacks_against_have_advantage for e in effects),
        any(e.attacks_against_have_disadvantage for e in effects),
    )


def outgoing_attack_advantage(conditions: Iterable[Condition]) -> Advantage:
    """The net Advantage state for an attack the creature **makes**.

    Combines every condition's effect on the creature's own attacks; mixed
    Advantage and Disadvantage cancel to :attr:`Advantage.NORMAL`.
    """
    effects = [CONDITION_EFFECTS[c] for c in conditions]
    return _combine_advantage(
        any(e.own_attacks_have_advantage for e in effects),
        any(e.own_attacks_have_disadvantage for e in effects),
    )


def attack_advantage(
    attacker_conditions: Iterable[Condition],
    target_conditions: Iterable[Condition],
) -> Advantage:
    """The net Advantage for an attack, composing BOTH combatants' conditions.

    Gathers every Advantage source (the attacker's own-attack effects + the
    effects of attacks *against* the target) and every Disadvantage source across
    both creatures, then applies the 2024 cancellation rule ONCE: any Advantage
    combined with any Disadvantage yields a normal roll. This is what an attack's
    resolution feeds to :func:`app.rules.attack.resolve_attack`.
    """
    attacker = [CONDITION_EFFECTS[c] for c in attacker_conditions]
    target = [CONDITION_EFFECTS[c] for c in target_conditions]
    has_advantage = any(e.own_attacks_have_advantage for e in attacker) or any(
        e.attacks_against_have_advantage for e in target
    )
    has_disadvantage = any(e.own_attacks_have_disadvantage for e in attacker) or any(
        e.attacks_against_have_disadvantage for e in target
    )
    return _combine_advantage(has_advantage, has_disadvantage)
