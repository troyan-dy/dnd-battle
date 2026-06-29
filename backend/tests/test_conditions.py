"""Unit tests for the pure D&D 2024 conditions rules module.

The conditions math is pure data + helpers (no RNG, no I/O); these tests pin the
2024 condition list, the mechanical-effect flags for the combat-relevant
conditions, the authoritative effects text, and the advantage-aggregation helpers
that compose with :class:`app.rules.attack.Advantage`.
"""

from __future__ import annotations

import pytest
from app.rules import (
    CONDITION_EFFECTS,
    Advantage,
    Condition,
    ConditionEffect,
    condition_effect,
    incoming_attack_advantage,
    outgoing_attack_advantage,
)


def test_condition_list_is_the_fifteen_2024_conditions() -> None:
    assert {c.value for c in Condition} == {
        "blinded",
        "charmed",
        "deafened",
        "exhaustion",
        "frightened",
        "grappled",
        "incapacitated",
        "invisible",
        "paralyzed",
        "petrified",
        "poisoned",
        "prone",
        "restrained",
        "stunned",
        "unconscious",
    }


def test_every_condition_has_a_described_effect() -> None:
    # The mapping is exhaustive over the enum and every entry self-identifies.
    assert set(CONDITION_EFFECTS) == set(Condition)
    for condition, effect in CONDITION_EFFECTS.items():
        assert isinstance(effect, ConditionEffect)
        assert effect.condition is condition
        assert effect.effects, f"{condition} should carry authoritative rules text"


def test_condition_effect_lookup_returns_mapping_entry() -> None:
    assert condition_effect(Condition.STUNNED) is CONDITION_EFFECTS[Condition.STUNNED]


@pytest.mark.parametrize(
    "condition",
    [
        Condition.PARALYZED,
        Condition.PETRIFIED,
        Condition.RESTRAINED,
        Condition.STUNNED,
        Condition.UNCONSCIOUS,
        Condition.BLINDED,
    ],
)
def test_conditions_that_grant_advantage_to_attackers(condition: Condition) -> None:
    assert CONDITION_EFFECTS[condition].attacks_against_have_advantage is True


def test_invisible_imposes_disadvantage_on_attackers_and_advantage_on_self() -> None:
    invisible = CONDITION_EFFECTS[Condition.INVISIBLE]
    assert invisible.attacks_against_have_disadvantage is True
    assert invisible.attacks_against_have_advantage is False
    assert invisible.own_attacks_have_advantage is True


@pytest.mark.parametrize(
    "condition",
    [
        Condition.INCAPACITATED,
        Condition.PARALYZED,
        Condition.PETRIFIED,
        Condition.STUNNED,
        Condition.UNCONSCIOUS,
    ],
)
def test_incapacitating_conditions_set_the_flag(condition: Condition) -> None:
    assert CONDITION_EFFECTS[condition].incapacitated is True


@pytest.mark.parametrize(
    "condition",
    [
        Condition.GRAPPLED,
        Condition.PARALYZED,
        Condition.PETRIFIED,
        Condition.RESTRAINED,
        Condition.STUNNED,
        Condition.UNCONSCIOUS,
    ],
)
def test_conditions_that_zero_speed(condition: Condition) -> None:
    assert CONDITION_EFFECTS[condition].speed_zero is True


def test_prone_does_not_zero_speed_but_imposes_self_disadvantage() -> None:
    prone = CONDITION_EFFECTS[Condition.PRONE]
    assert prone.speed_zero is False
    assert prone.own_attacks_have_disadvantage is True
    # The distance-dependent attacks-against nuance is not an unconditional flag.
    assert prone.attacks_against_have_advantage is False
    assert prone.attacks_against_have_disadvantage is False


@pytest.mark.parametrize(
    "condition",
    [
        Condition.PARALYZED,
        Condition.PETRIFIED,
        Condition.STUNNED,
        Condition.UNCONSCIOUS,
    ],
)
def test_conditions_that_auto_fail_str_and_dex_saves(condition: Condition) -> None:
    effect = CONDITION_EFFECTS[condition]
    assert effect.auto_fails_strength_saves is True
    assert effect.auto_fails_dexterity_saves is True


def test_restrained_only_auto_fails_dex_saves() -> None:
    restrained = CONDITION_EFFECTS[Condition.RESTRAINED]
    assert restrained.auto_fails_dexterity_saves is False  # Disadvantage, not auto-fail
    assert restrained.auto_fails_strength_saves is False


@pytest.mark.parametrize(
    "condition",
    [Condition.PARALYZED, Condition.UNCONSCIOUS],
)
def test_conditions_with_melee_auto_crit(condition: Condition) -> None:
    assert CONDITION_EFFECTS[condition].melee_attacks_against_are_critical is True


def test_poisoned_imposes_check_and_attack_disadvantage() -> None:
    poisoned = CONDITION_EFFECTS[Condition.POISONED]
    assert poisoned.own_attacks_have_disadvantage is True
    assert poisoned.ability_checks_have_disadvantage is True


# --- aggregate advantage helpers -------------------------------------------------


def test_incoming_attack_advantage_with_no_conditions_is_normal() -> None:
    assert incoming_attack_advantage([]) is Advantage.NORMAL


def test_incoming_attack_advantage_from_advantage_condition() -> None:
    assert incoming_attack_advantage([Condition.PRONE, Condition.RESTRAINED]) is Advantage.ADVANTAGE


def test_incoming_attack_advantage_from_disadvantage_condition() -> None:
    assert incoming_attack_advantage([Condition.INVISIBLE]) is Advantage.DISADVANTAGE


def test_incoming_attack_advantage_cancels_when_both_present() -> None:
    # Restrained (advantage against) + Invisible (disadvantage against) cancel out.
    assert (
        incoming_attack_advantage([Condition.RESTRAINED, Condition.INVISIBLE]) is Advantage.NORMAL
    )


def test_outgoing_attack_advantage_with_no_conditions_is_normal() -> None:
    assert outgoing_attack_advantage([]) is Advantage.NORMAL


def test_outgoing_attack_advantage_from_advantage_condition() -> None:
    assert outgoing_attack_advantage([Condition.INVISIBLE]) is Advantage.ADVANTAGE


def test_outgoing_attack_advantage_from_disadvantage_condition() -> None:
    assert outgoing_attack_advantage([Condition.POISONED]) is Advantage.DISADVANTAGE


def test_outgoing_attack_advantage_cancels_when_both_present() -> None:
    # Invisible (own advantage) + Poisoned (own disadvantage) cancel out.
    assert outgoing_attack_advantage([Condition.INVISIBLE, Condition.POISONED]) is Advantage.NORMAL


def test_condition_effect_is_frozen() -> None:
    with pytest.raises(AttributeError):
        CONDITION_EFFECTS[Condition.PRONE].speed_zero = True  # type: ignore[misc]
