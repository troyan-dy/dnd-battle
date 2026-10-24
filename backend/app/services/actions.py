"""Apply a VALIDATED Action's durable effect to the source-of-truth rows.

CLAUDE.md rule 1 (server is authoritative): an intent is first authorised by
:func:`app.services.intents.validate_intent`; only then does
:func:`apply_action` mutate the durable :class:`Token` / :class:`Character` /
:class:`Room` rows, BEFORE the action is broadcast. This keeps
:func:`app.services.board.build_board_state` authoritative, so a client that
reloads its link mid-encounter rebuilds the post-action board (reconnect-safe,
CLAUDE.md rule 2). Attacks are resolved separately by
:func:`app.services.attacks.resolve_attack` (they roll dice).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.room import Room
from app.models.token import Token
from app.schemas.action import ActionPayload
from app.schemas.payloads import (
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MovePayload,
    SetVisibilityPayload,
)
from app.services.initiative import advance_turn

# The actions whose durable effect lands on a single token (or its character).
TokenActionPayload = MovePayload | DamagePayload | HealPayload | SetVisibilityPayload


async def apply_action(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    payload: ActionPayload,
) -> None:
    """Apply a VALIDATED action's durable effect to the source-of-truth rows.

    Called only after :func:`app.services.intents.validate_intent` has authorised
    ``payload``, and BEFORE the action is broadcast, so the durable :class:`Token` /
    :class:`Character` rows reflect the change. The caller commits.

    * ``move``    -> update the token's grid coordinates.
    * ``damage``  -> reduce the bound character's current HP, clamped at 0.
    * ``heal``    -> restore the bound character's current HP, clamped at max HP.
    * ``setVisibility`` -> flip the token's ``hidden`` flag (fog of war).
    * ``endTurn`` -> advance the room's initiative pointer to the next combatant.
    * ``mark``    -> transient ping, carries no durable board state -> no row change.

    The ``None`` guards are defensive: validation already proved the token (and
    thus its character) exists in ``room_id``.
    """
    if isinstance(payload, (MovePayload, DamagePayload, HealPayload, SetVisibilityPayload)):
        token = await session.get(Token, payload.token_id)
        if token is not None and token.room_id == room_id:
            await _apply_to_token(session, token=token, payload=payload)
    elif isinstance(payload, EndTurnPayload):
        room = await session.get(Room, room_id)
        if room is not None:
            await advance_turn(session, room=room)


async def _apply_to_token(
    session: AsyncSession,
    *,
    token: Token,
    payload: TokenActionPayload,
) -> None:
    """Apply a token action's effect to ``token`` (or to the character it binds)."""
    if isinstance(payload, MovePayload):
        token.x = payload.x
        token.y = payload.y
    elif isinstance(payload, SetVisibilityPayload):
        token.hidden = payload.hidden
    else:
        character = await session.get(Character, token.character_id)
        if character is not None:
            character.current_hp = _hit_points_after(character, payload)


def _hit_points_after(character: Character, payload: DamagePayload | HealPayload) -> int:
    """The character's HP after ``payload``: damage clamps at 0, healing at max HP."""
    if isinstance(payload, DamagePayload):
        return max(0, character.current_hp - payload.amount)
    return min(character.max_hp, character.current_hp + payload.amount)
