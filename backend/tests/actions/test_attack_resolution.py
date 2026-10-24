"""Tests for server-side attack resolution (``app.services.attacks.resolve_attack``).

Dice are scripted so the d20 and damage rolls are deterministic; the target's
durable HP, AC, resistances and conditions come from the seeded database.
"""

from __future__ import annotations

from app.models import (
    Character,
)
from app.schemas.attack import AttackIntentPayload
from app.services.attacks import resolve_attack

from tests.actions.support import Seeded
from tests.support import ScriptedRandom


async def test_resolve_attack_hit_rolls_and_applies_damage(seeded: Seeded) -> None:
    """On a hit (total >= AC) the rolled damage is applied to the target (clamped)."""
    # char2 has the default AC 10; d20=15 + bonus 4 = 19 -> hit; damage dice 6,6.
    rng = ScriptedRandom([15, 6, 6])
    async with seeded.factory() as session:
        outcome = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                attack_bonus=4,
                damage="2d6+1",
            ),
            rng=rng,
        )
        await session.commit()

    assert outcome.attack_roll == 15
    assert outcome.attack_total == 19
    assert outcome.armor_class == 10
    assert outcome.is_hit is True
    assert outcome.is_critical_hit is False
    assert outcome.advantage.value == "normal"
    assert outcome.damage_rolls == [6, 6]
    assert outcome.damage_total == 13  # 6 + 6 + 1 modifier, no defense
    assert outcome.defense.value == "normal"

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30 - 13


async def test_resolve_attack_miss_applies_no_damage(seeded: Seeded) -> None:
    """A miss (total < AC, not a natural 20) rolls no damage and leaves HP untouched."""
    # d20=2 + bonus 0 = 2 < AC 10 -> miss; no damage dice are rolled.
    rng = ScriptedRandom([2])
    async with seeded.factory() as session:
        outcome = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="2d6+1",
            ),
            rng=rng,
        )
        await session.commit()

    assert outcome.is_hit is False
    assert outcome.damage_rolls == []
    assert outcome.damage_total == 0

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30  # unchanged


async def test_resolve_attack_natural_20_always_hits(seeded: Seeded) -> None:
    """A natural 20 hits regardless of AC and is flagged a critical hit."""
    rng = ScriptedRandom([20, 4])
    async with seeded.factory() as session:
        outcome = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                attack_bonus=-20,  # would miss on totals, but a nat 20 always hits
                damage="1d6",
            ),
            rng=rng,
        )
        await session.commit()

    assert outcome.is_hit is True
    assert outcome.is_critical_hit is True
    assert outcome.damage_total == 4


async def test_resolve_attack_applies_target_resistance(seeded: Seeded) -> None:
    """A target's resistance to the damage type halves the rolled damage (rounded down)."""
    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        target.resistances = {"fire": "resistance"}
        await session.commit()

    # hit (d20=18); damage 2d6 -> 5 + 6 = 11 raw, resisted -> 5.
    rng = ScriptedRandom([18, 5, 6])
    async with seeded.factory() as session:
        outcome = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="2d6",
                damage_type="fire",  # type: ignore[arg-type]
            ),
            rng=rng,
        )
        await session.commit()

    assert outcome.is_hit is True
    assert outcome.defense.value == "resistance"
    assert outcome.damage_type.value == "fire"
    assert outcome.damage_total == 5  # 11 // 2

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30 - 5


async def test_resolve_attack_advantage_from_target_condition(seeded: Seeded) -> None:
    """A restrained target grants attacks against it advantage (two d20s, higher used)."""
    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        target.conditions = ["restrained"]
        await session.commit()

    # advantage rolls two d20s (3, 17) and uses the higher (17); then 1d6 -> 4.
    rng = ScriptedRandom([3, 17, 4])
    async with seeded.factory() as session:
        outcome = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="1d6",
            ),
            rng=rng,
        )
        await session.commit()

    assert outcome.advantage.value == "advantage"
    assert outcome.attack_roll == 17  # the higher of the two d20s
    assert outcome.is_hit is True
    assert outcome.damage_total == 4
