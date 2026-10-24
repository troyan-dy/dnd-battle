"""Fog of war: which actions must stay hidden from players (CLAUDE.md rule 3).

A host may hide a token; the server then never broadcasts that token's movement,
HP changes or attack participation to players. This module answers "does this
action touch a hidden token?" from the durable :class:`Token` rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import Token
from app.schemas.action import IntentActionPayload
from app.schemas.attack import AttackIntentPayload
from app.schemas.payloads import DamagePayload, HealPayload, MovePayload


async def action_hidden_from_players(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    payload: IntentActionPayload,
) -> bool:
    """Whether a (non-visibility) action references a token hidden from players.

    Such an action is broadcast to hosts only, so a hidden token's movement / HP /
    attack participation never leaks to players (fog of war, CLAUDE.md rule 3). An
    attack is hidden when EITHER the attacker or the target is a hidden token.
    """
    if isinstance(payload, (MovePayload, DamagePayload, HealPayload)):
        return await _token_hidden(session, room_id=room_id, token_id=payload.token_id)
    if isinstance(payload, AttackIntentPayload):
        if await _token_hidden(session, room_id=room_id, token_id=payload.attacker_token_id):
            return True
        return await _token_hidden(session, room_id=room_id, token_id=payload.target_token_id)
    return False


async def _token_hidden(session: AsyncSession, *, room_id: uuid.UUID, token_id: uuid.UUID) -> bool:
    """Whether ``token_id`` exists in ``room_id`` and is currently hidden from players."""
    token = await session.get(Token, token_id)
    return token is not None and token.room_id == room_id and token.hidden
