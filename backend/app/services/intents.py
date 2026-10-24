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
raised; the transport layer maps it to an error ack and does NOT broadcast. On
success the validated :class:`ActionPayload` is returned, ready for the server to
stamp into a broadcast :class:`Action`.

Validation reads the durable :class:`Token` rows — the same source of truth
:func:`app.services.board.build_board_state` reads; applying the validated action
is :func:`app.services.actions.apply_action`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ParticipantRole
from app.models.room import Room
from app.models.token import Token
from app.schemas.action import ActionIntent, ActionPayload
from app.schemas.attack import AttackIntentPayload
from app.schemas.payloads import (
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MovePayload,
    SetVisibilityPayload,
)
from app.services.initiative import active_character_id

# Uniform rejection messages. Kept generic so a player cannot probe the board for
# tokens they do not own (the "not on this board" vs "not yours" distinction is
# intentionally coarse to avoid leaking which tokens exist).
_TOKEN_NOT_ON_BOARD = "Target token is not on this board."
_TOKEN_NOT_OWNED = "You can only act on your own token."
# Whose-turn enforcement for `endTurn` (the turn order is public in BoardState, so
# these messages leak nothing a participant cannot already see in the tracker).
_COMBAT_NOT_STARTED = "Combat has not started."
_NOT_YOUR_TURN = "It is not your turn."
# Fog of war: only the host (DM) may hide/reveal tokens (CLAUDE.md rule 3).
_VISIBILITY_HOST_ONLY = "Only the host can change token visibility."


class IntentValidationError(Exception):
    """A client intent failed permission / state validation; do NOT broadcast it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _controlled_token_id(payload: ActionPayload) -> uuid.UUID | None:
    """The token the actor must control to issue ``payload`` (``None`` if none).

    ``move`` / ``damage`` / ``heal`` act on their token; an attack is authorised by
    the ATTACKER token (same rule as move/damage). Other actions name no such token.
    """
    if isinstance(payload, (MovePayload, DamagePayload, HealPayload)):
        return payload.token_id
    if isinstance(payload, AttackIntentPayload):
        return payload.attacker_token_id
    return None


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
    controlled_token_id = _controlled_token_id(payload)
    if controlled_token_id is not None:
        await _authorize_token_target(
            session,
            room_id=room_id,
            role=role,
            character_id=character_id,
            token_id=controlled_token_id,
        )

    # An attack's TARGET only has to be a token on this board — you may attack
    # anyone (whose-turn gating is left to the initiative-driven flow).
    if isinstance(payload, AttackIntentPayload):
        await _require_token_in_room(session, room_id=room_id, token_id=payload.target_token_id)
    # Ending a turn is gated by whose turn it is: the host may always advance the
    # order; a player may only end the turn of their OWN active combatant.
    elif isinstance(payload, EndTurnPayload):
        await _authorize_end_turn(session, room_id=room_id, role=role, character_id=character_id)
    # Hiding/revealing a token is fog of war — HOST-ONLY (CLAUDE.md rule 3). The
    # token must also exist on this board.
    elif isinstance(payload, SetVisibilityPayload):
        await _authorize_visibility(session, room_id=room_id, role=role, token_id=payload.token_id)
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


async def _authorize_visibility(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    role: ParticipantRole,
    token_id: uuid.UUID,
) -> None:
    """Ensure only the host hides/reveals a token, and that it is on this board."""
    if role != ParticipantRole.host:
        raise IntentValidationError(_VISIBILITY_HOST_ONLY)
    await _require_token_in_room(session, room_id=room_id, token_id=token_id)


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
