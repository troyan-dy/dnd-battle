"""Server-side attack resolution through the isolated rules engine.

Server-authoritative roll (CLAUDE.md rule 1): the d20 and damage dice are rolled
HERE with an injected ``rng`` — the client never supplies them. The rules engine
(CLAUDE.md rule 4) does all the tabletop math; this module only loads the two
combatants, feeds the engine and applies the resulting damage to the durable row.
"""

from __future__ import annotations

import random
import uuid
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.token import Token
from app.rules import AttackRoll, Condition, DamageResult, Defense, attack_advantage, resolve_damage
from app.rules import resolve_attack as roll_attack
from app.schemas.attack import AttackIntentPayload, AttackResultPayload
from app.schemas.character import ARMOR_CLASS_DEFAULT


async def resolve_attack(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    payload: AttackIntentPayload,
    rng: random.Random,
) -> AttackResultPayload:
    """Roll a VALIDATED attack through the rules engine and return the broadcast result.

    Server-authoritative roll (CLAUDE.md rule 1): the d20 and damage dice are rolled
    HERE with the injected ``rng`` — the client never supplies them. The rules engine
    (CLAUDE.md rule 4) does all the tabletop math:

    * advantage/disadvantage is derived from BOTH combatants' conditions via
      :func:`app.rules.conditions.attack_advantage`;
    * :func:`app.rules.attack.resolve_attack` rolls the d20 against the TARGET's
      Armor Class (natural 20 always hits, natural 1 always misses);
    * ONLY on a hit is damage rolled via :func:`app.rules.damage.resolve_damage`,
      reduced by the target's resistance/vulnerability/immunity for the damage type.

    The resulting damage is applied to the target character's durable HP (clamped at
    0) BEFORE broadcast, so :func:`app.services.board.build_board_state` stays
    authoritative and a reconnecting client rebuilds the post-attack board
    (reconnect-safe, CLAUDE.md rule 2). The caller commits.

    The ``None`` guards are defensive: :func:`app.services.intents.validate_intent`
    already proved both tokens (and the target's character) exist in ``room_id``.
    """
    attacker = await _token_character(session, room_id=room_id, token_id=payload.attacker_token_id)
    target = await _token_character(session, room_id=room_id, token_id=payload.target_token_id)

    roll = _roll_to_hit(attacker, target, payload=payload, rng=rng)
    damage = _no_damage(payload)
    if roll.is_hit:
        damage = _roll_damage(target, payload=payload, rng=rng)
        if target is not None:
            target.current_hp = max(0, target.current_hp - damage.total)

    return AttackResultPayload(
        attacker_token_id=payload.attacker_token_id,
        target_token_id=payload.target_token_id,
        attack_roll=roll.d20,
        attack_bonus=payload.attack_bonus,
        attack_total=roll.total,
        advantage=roll.advantage,
        armor_class=roll.armor_class,
        is_hit=roll.is_hit,
        is_critical_hit=roll.is_critical_hit,
        is_critical_miss=roll.is_critical_miss,
        damage=payload.damage,
        damage_type=payload.damage_type,
        defense=damage.defense,
        damage_rolls=list(damage.rolls),
        damage_total=damage.total,
    )


async def _token_character(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    token_id: uuid.UUID,
) -> Character | None:
    """The character bound to ``token_id`` if that token is on ``room_id``'s board."""
    token = await session.get(Token, token_id)
    if token is None or token.room_id != room_id:
        return None
    return await session.get(Character, token.character_id)


def _conditions_of(character: Character | None) -> list[Condition]:
    """Map a character's stored condition names to :class:`Condition`, ignoring unknowns.

    Defensive: a stale or unrecognised condition name (e.g. from an older client)
    is silently skipped rather than crashing attack resolution.
    """
    parsed: list[Condition] = []
    if character is None:
        return parsed
    for name in character.conditions:
        with suppress(ValueError):
            parsed.append(Condition(name))
    return parsed


def _roll_to_hit(
    attacker: Character | None,
    target: Character | None,
    *,
    payload: AttackIntentPayload,
    rng: random.Random,
) -> AttackRoll:
    """Roll the d20 against the target's AC with condition-derived advantage."""
    return roll_attack(
        armor_class=ARMOR_CLASS_DEFAULT if target is None else target.armor_class,
        attack_bonus=payload.attack_bonus,
        advantage=attack_advantage(_conditions_of(attacker), _conditions_of(target)),
        rng=rng,
    )


def _roll_damage(
    target: Character | None,
    *,
    payload: AttackIntentPayload,
    rng: random.Random,
) -> DamageResult:
    """Roll a hit's damage, reduced by the target's defense against its damage type."""
    resistances = {} if target is None else target.resistances
    return resolve_damage(
        expression=payload.damage,
        damage_type=payload.damage_type,
        defense=_target_defense(resistances, payload),
        rng=rng,
    )


def _no_damage(payload: AttackIntentPayload) -> DamageResult:
    """The damage outcome of a miss: nothing rolled, nothing taken, no defense."""
    return DamageResult(
        rolls=(),
        modifier=0,
        damage_type=payload.damage_type,
        defense=Defense.NORMAL,
        raw_total=0,
        total=0,
    )


def _target_defense(resistances: dict[str, object], payload: AttackIntentPayload) -> Defense:
    """The target's :class:`Defense` against the attack's damage type (``NORMAL`` if absent)."""
    raw = resistances.get(payload.damage_type.value)
    if not isinstance(raw, str):
        return Defense.NORMAL
    try:
        return Defense(raw)
    except ValueError:
        return Defense.NORMAL
