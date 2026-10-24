"""Carry out one client intent against the durable, server-authoritative rows.

The realtime transport authenticates the actor and emits the results; everything
in between — validating the intent, applying its durable effect (rolling an
attack through the rules engine), allocating the broadcast ``seq`` and deciding
whether fog of war restricts the broadcast to hosts — happens here, inside the
caller's DB session, so the transport layer holds no business logic.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import final

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ParticipantRole
from app.schemas.action import Action, ActionIntent, ActionPayload, BroadcastActionPayload
from app.schemas.attack import AttackIntentPayload
from app.schemas.board import BoardState
from app.schemas.payloads import (
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MarkPayload,
    MovePayload,
    SetVisibilityPayload,
)
from app.services import actions, attacks, board, intents, sequence, visibility

# Every intent except `setVisibility`, which is never rebroadcast as an Action.
BoardActionPayload = (
    MovePayload | MarkPayload | DamagePayload | HealPayload | AttackIntentPayload | EndTurnPayload
)


@dataclass(frozen=True)
class CommittedAction:
    """A committed action ready to broadcast, and whether only hosts may see it."""

    action: Action
    hosts_only: bool


@dataclass(frozen=True)
class RoleBoards:
    """The full host board and the fog-filtered player board after a resync."""

    host: BoardState
    player: BoardState


@final
class ActionDispatcher:
    """Validate and apply client intents within one DB session (the caller emits)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        sequencer: sequence.SequenceCounter,
        rng: random.Random,
    ) -> None:
        self._session = session
        self._sequencer = sequencer
        self._rng = rng

    async def validate(
        self,
        intent: ActionIntent,
        *,
        room_id: uuid.UUID,
        role: ParticipantRole,
        character_id: uuid.UUID | None,
    ) -> ActionPayload:
        """Authorise ``intent``; raises :class:`app.services.intents.IntentValidationError`."""
        return await intents.validate_intent(
            self._session,
            room_id=room_id,
            role=role,
            character_id=character_id,
            intent=intent,
        )

    async def resync_visibility(
        self,
        payload: SetVisibilityPayload,
        *,
        room_id: uuid.UUID,
    ) -> RoleBoards:
        """Flip the token's hidden flag, commit, and build each role's BoardState.

        Players never receive a hidden token, hosts get the full board (CLAUDE.md
        rule 3, server-enforced).
        """
        await actions.apply_action(self._session, room_id=room_id, payload=payload)
        host_board = await board.build_board_state(self._session, room_id, include_hidden=True)
        player_board = await board.build_board_state(
            self._session,
            room_id,
            include_hidden=False,
        )
        await self._session.commit()
        return RoleBoards(host=host_board, player=player_board)

    async def commit(
        self,
        payload: BoardActionPayload,
        *,
        room_id: uuid.UUID,
        actor_participant_id: uuid.UUID,
    ) -> CommittedAction:
        """Apply ``payload``, persist its ``seq`` and stamp the broadcast :class:`Action`."""
        broadcast_payload = await self._apply(payload, room_id=room_id)
        # Allocate the broadcast seq and persist the room's high-water mark in the
        # SAME transaction as the durable effect, so the sequence survives a restart.
        seq = await sequence.reserve_action_seq(
            self._session,
            room_id=room_id,
            sequencer=self._sequencer,
        )
        # Fog of war: if this action touches a token currently hidden from players,
        # it is broadcast to HOSTS only so the hidden token never leaks (rule 3).
        hosts_only = await visibility.action_hidden_from_players(
            self._session,
            room_id=room_id,
            payload=payload,
        )
        await self._session.commit()
        stamped = Action(
            id=uuid.uuid4(),
            room_id=room_id,
            actor_participant_id=actor_participant_id,
            seq=seq,
            payload=broadcast_payload,
        )
        return CommittedAction(action=stamped, hosts_only=hosts_only)

    async def _apply(
        self,
        payload: BoardActionPayload,
        *,
        room_id: uuid.UUID,
    ) -> BroadcastActionPayload:
        """Apply ``payload``'s durable effect and return what to broadcast for it.

        An attack is RESOLVED server-side (dice rolled here, damage applied) and
        broadcast as its result payload; every other action's durable effect is
        applied and the validated intent payload is broadcast unchanged.
        """
        if isinstance(payload, AttackIntentPayload):
            return await attacks.resolve_attack(
                self._session,
                room_id=room_id,
                payload=payload,
                rng=self._rng,
            )
        await actions.apply_action(self._session, room_id=room_id, payload=payload)
        return payload
