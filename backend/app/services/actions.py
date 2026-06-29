"""Server-side validation of client Action intents (permissions + bounds).

CLAUDE.md rule 1 (server is authoritative) + rule 3 (permissions): a client sends
an :class:`ActionIntent`; before the server broadcasts the resulting
:class:`Action`, it must validate that intent against the current board state and
the actor's permissions. This module is that authoritative gate — a pure,
fully-unit-tested function isolated from the transport and UI layers.

What is validated WHERE:

* Protocol ``version``, coordinate / damage-amount bounds and unknown action types
  are rejected at **parse** time by :class:`ActionIntent` and the payload
  discriminated union (:mod:`app.schemas.action`).
* This module adds the **state-aware** + **permission** checks that need the live
  board:

  - the referenced token actually exists and belongs to the *actor's* room
    (applies to ``move``, ``damage`` and ``heal``);
  - a ``player`` may only target a token bound to their OWN character; a ``host``
    may target any token in the room (CLAUDE.md rule 3);
  - ``mark`` carries no token, so any authenticated participant in the room may
    issue it (a transient ping);
  - ``endTurn`` is gated by whose turn it is: the host may always advance the
    order, a player only when their own combatant is active (Phase 5 initiative).

On rejection a :class:`IntentValidationError` carrying a human-readable reason is
raised; the transport layer (the next Phase 4 task) maps it to an error ack and
does NOT broadcast. On success the validated :class:`ActionPayload` is returned,
ready for the server to stamp into a broadcast :class:`Action`.

This task deliberately does NOT introduce a live mutable in-memory BoardState or
any broadcasting: it validates against the durable :class:`Token` rows — the same
source of truth :func:`app.services.board.build_board_state` reads. Mutation and
broadcast are the next Phase 4 tasks.
"""

from __future__ import annotations

import random
import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.enums import ParticipantRole
from app.models.room import Room
from app.models.token import Token
from app.rules.attack import resolve_attack as roll_attack
from app.rules.conditions import Condition, attack_advantage
from app.rules.damage import DamageType, Defense, resolve_damage
from app.schemas.action import (
    ActionIntent,
    ActionPayload,
    AttackIntentPayload,
    AttackResultPayload,
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MovePayload,
)
from app.schemas.room import ARMOR_CLASS_DEFAULT
from app.services.initiative import active_character_id, advance_turn

# Uniform rejection messages. Kept generic so a player cannot probe the board for
# tokens they do not own (the "not on this board" vs "not yours" distinction is
# intentionally coarse to avoid leaking which tokens exist).
_TOKEN_NOT_ON_BOARD = "Target token is not on this board."
_TOKEN_NOT_OWNED = "You can only act on your own token."
# Whose-turn enforcement for `endTurn` (the turn order is public in BoardState, so
# these messages leak nothing a participant cannot already see in the tracker).
_COMBAT_NOT_STARTED = "Combat has not started."
_NOT_YOUR_TURN = "It is not your turn."


class IntentValidationError(Exception):
    """A client intent failed permission / state validation; do NOT broadcast it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def validate_intent(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    role: ParticipantRole,
    character_id: uuid.UUID | None,
    intent: ActionIntent,
) -> ActionPayload:
    """Validate an authenticated client's intent against state + permissions.

    ``room_id`` / ``role`` / ``character_id`` come from the server-authenticated
    join (the resolved invite), never from the client payload. Returns the
    validated :class:`ActionPayload` on success; raises :class:`IntentValidationError`
    (with a human-readable ``reason``) on any permission / state violation.
    """
    payload = intent.payload

    # Token-targeting actions must reference a token in the actor's room that the
    # actor is permitted to act on.
    if isinstance(payload, (MovePayload, DamagePayload, HealPayload)):
        await _authorize_token_target(
            session,
            room_id=room_id,
            role=role,
            character_id=character_id,
            token_id=payload.token_id,
        )
    # An attack is authorised by the ATTACKER token (the actor must control it, same
    # rule as move/damage); the TARGET only has to be a token on this board — you may
    # attack anyone (whose-turn gating is left to the initiative-driven flow).
    elif isinstance(payload, AttackIntentPayload):
        await _authorize_token_target(
            session,
            room_id=room_id,
            role=role,
            character_id=character_id,
            token_id=payload.attacker_token_id,
        )
        await _require_token_in_room(session, room_id=room_id, token_id=payload.target_token_id)
    # Ending a turn is gated by whose turn it is: the host may always advance the
    # order; a player may only end the turn of their OWN active combatant.
    elif isinstance(payload, EndTurnPayload):
        await _authorize_end_turn(session, room_id=room_id, role=role, character_id=character_id)
    # `mark` carries no token and is allowed for any room participant (a ping).

    return payload


async def _authorize_token_target(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    role: ParticipantRole,
    character_id: uuid.UUID | None,
    token_id: uuid.UUID,
) -> None:
    """Ensure the token exists in ``room_id`` and the actor may act on it.

    Host may act on any token in their room; a player only on the token bound to
    their own character. Raises :class:`IntentValidationError` otherwise.
    """
    token = await session.get(Token, token_id)
    if token is None or token.room_id != room_id:
        raise IntentValidationError(_TOKEN_NOT_ON_BOARD)

    if role == ParticipantRole.host:
        return

    # Player: the token must be bound to this participant's own character.
    if character_id is None or token.character_id != character_id:
        raise IntentValidationError(_TOKEN_NOT_OWNED)


async def _require_token_in_room(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    token_id: uuid.UUID,
) -> None:
    """Ensure ``token_id`` exists and belongs to ``room_id`` (no ownership check).

    Used for an attack's TARGET: any token on this board is a legal target. Raises
    :class:`IntentValidationError` with the generic on-board message otherwise.
    """
    token = await session.get(Token, token_id)
    if token is None or token.room_id != room_id:
        raise IntentValidationError(_TOKEN_NOT_ON_BOARD)


async def _authorize_end_turn(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    role: ParticipantRole,
    character_id: uuid.UUID | None,
) -> None:
    """Ensure the actor may end the current turn (CLAUDE.md rule 3).

    The host may always advance the order. A player may end the turn only when it
    is currently their OWN combatant's turn. Raises :class:`IntentValidationError`
    otherwise.
    """
    if role == ParticipantRole.host:
        return

    room = await session.get(Room, room_id)
    if room is None or room.initiative_active_index is None:
        raise IntentValidationError(_COMBAT_NOT_STARTED)

    if character_id is None or await active_character_id(session, room) != character_id:
        raise IntentValidationError(_NOT_YOUR_TURN)


async def apply_action(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    payload: ActionPayload,
) -> None:
    """Apply a VALIDATED action's durable effect to the source-of-truth rows.

    Called only after :func:`validate_intent` has authorised ``payload``, and
    BEFORE the action is broadcast, so the durable :class:`Token` / :class:`Character`
    rows reflect the change. This keeps :func:`app.services.board.build_board_state`
    authoritative: a client that reloads its link mid-encounter rebuilds the
    post-action board (reconnect-safe, CLAUDE.md rule 2). The caller commits.

    * ``move``    -> update the token's grid coordinates.
    * ``damage``  -> reduce the bound character's current HP, clamped at 0.
    * ``heal``    -> restore the bound character's current HP, clamped at max HP.
    * ``endTurn`` -> advance the room's initiative pointer to the next combatant.
    * ``mark``    -> transient ping, carries no durable board state -> no row change.

    The ``None`` guards are defensive: validation already proved the token (and
    thus its character) exists in ``room_id``.
    """
    if isinstance(payload, MovePayload):
        token = await session.get(Token, payload.token_id)
        if token is not None and token.room_id == room_id:
            token.x = payload.x
            token.y = payload.y
    elif isinstance(payload, DamagePayload):
        token = await session.get(Token, payload.token_id)
        if token is not None and token.room_id == room_id:
            character = await session.get(Character, token.character_id)
            if character is not None:
                character.current_hp = max(0, character.current_hp - payload.amount)
    elif isinstance(payload, HealPayload):
        token = await session.get(Token, payload.token_id)
        if token is not None and token.room_id == room_id:
            character = await session.get(Character, token.character_id)
            if character is not None:
                character.current_hp = min(character.max_hp, character.current_hp + payload.amount)
    elif isinstance(payload, EndTurnPayload):
        room = await session.get(Room, room_id)
        if room is not None:
            await advance_turn(session, room=room)


class SequenceCounter(Protocol):
    """Structural type for the in-memory per-room sequence cache.

    Declared here (rather than importing the concrete ``RoomSequencer`` from the
    realtime layer) so this service does not depend on the transport layer — the
    realtime layer already depends on this service, and importing back would create
    a cycle. :class:`app.realtime.sequence.RoomSequencer` satisfies it structurally.
    """

    def seed(self, room_id: str, next_seq: int) -> None: ...

    def next_seq(self, room_id: str) -> int: ...


async def reserve_action_seq(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    sequencer: SequenceCounter,
) -> int:
    """Allocate the next broadcast ``seq`` for a room, persisting the high-water mark.

    The durable :class:`Room.last_action_seq` column is the source of truth so the
    action sequence survives a server restart (CLAUDE.md rule 2). The in-memory
    ``sequencer`` is a fast cache: it is first SEEDED from the persisted value (a
    no-op once this process is warm, but the recovery path after a restart), then
    asked for the next number; the row is bumped to the new high-water. The caller
    commits this in the SAME transaction as the action's durable effect, so a crash
    between applying the action and persisting its ``seq`` cannot occur.

    The ``None`` guard is defensive: the actor's identity came from a resolved invite
    so the room exists; if it somehow does not, fall back to the in-memory counter
    rather than fail mid-broadcast.
    """
    room_key = str(room_id)
    room = await session.get(Room, room_id)
    if room is None:
        return sequencer.next_seq(room_key)
    sequencer.seed(room_key, room.last_action_seq)
    seq = sequencer.next_seq(room_key)
    room.last_action_seq = seq + 1
    return seq


def _parse_conditions(raw: list[str]) -> list[Condition]:
    """Map stored condition-name strings to :class:`Condition`, ignoring unknowns.

    Defensive: a stale or unrecognised condition name (e.g. from an older client)
    is silently skipped rather than crashing attack resolution.
    """
    parsed: list[Condition] = []
    for name in raw:
        try:
            parsed.append(Condition(name))
        except ValueError:
            continue
    return parsed


def _target_defense(resistances: dict[str, object], damage_type: DamageType) -> Defense:
    """The target's :class:`Defense` against ``damage_type`` (``NORMAL`` if absent/invalid)."""
    raw = resistances.get(damage_type.value)
    if not isinstance(raw, str):
        return Defense.NORMAL
    try:
        return Defense(raw)
    except ValueError:
        return Defense.NORMAL


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

    The ``None`` guards are defensive: :func:`validate_intent` already proved both
    tokens (and the target's character) exist in ``room_id``.
    """
    attacker_conditions: list[Condition] = []
    attacker_token = await session.get(Token, payload.attacker_token_id)
    if attacker_token is not None and attacker_token.room_id == room_id:
        attacker_char = await session.get(Character, attacker_token.character_id)
        if attacker_char is not None:
            attacker_conditions = _parse_conditions(attacker_char.conditions)

    target_char: Character | None = None
    armor_class = ARMOR_CLASS_DEFAULT
    target_conditions: list[Condition] = []
    target_token = await session.get(Token, payload.target_token_id)
    if target_token is not None and target_token.room_id == room_id:
        target_char = await session.get(Character, target_token.character_id)
        if target_char is not None:
            armor_class = target_char.armor_class
            target_conditions = _parse_conditions(target_char.conditions)

    advantage = attack_advantage(attacker_conditions, target_conditions)
    roll = roll_attack(
        armor_class=armor_class,
        attack_bonus=payload.attack_bonus,
        advantage=advantage,
        rng=rng,
    )

    damage_rolls: list[int] = []
    damage_total = 0
    defense = Defense.NORMAL
    if roll.is_hit:
        resistances = target_char.resistances if target_char is not None else {}
        defense = _target_defense(resistances, payload.damage_type)
        damage = resolve_damage(
            expression=payload.damage,
            damage_type=payload.damage_type,
            defense=defense,
            rng=rng,
        )
        damage_rolls = list(damage.rolls)
        damage_total = damage.total
        if target_char is not None:
            target_char.current_hp = max(0, target_char.current_hp - damage_total)

    return AttackResultPayload(
        attacker_token_id=payload.attacker_token_id,
        target_token_id=payload.target_token_id,
        attack_roll=roll.d20,
        attack_bonus=payload.attack_bonus,
        attack_total=roll.total,
        advantage=advantage,
        armor_class=armor_class,
        is_hit=roll.is_hit,
        is_critical_hit=roll.is_critical_hit,
        is_critical_miss=roll.is_critical_miss,
        damage=payload.damage,
        damage_type=payload.damage_type,
        defense=defense,
        damage_rolls=damage_rolls,
        damage_total=damage_total,
    )
