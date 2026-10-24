"""Tests for server-side Action intent validation (permissions + bounds).

Exercises ``app.services.intents.validate_intent`` against a seeded in-memory
database: host can target any token in its room, a player only its own token,
cross-owner / cross-room / unknown tokens are rejected, and non-token actions
(mark, endTurn) are allowed for any authenticated participant.
"""

from __future__ import annotations

import uuid

import pytest
from app.models import (
    InitiativeEntry,
    ParticipantRole,
    Room,
)
from app.schemas.action import ActionIntent
from app.schemas.attack import AttackIntentPayload
from app.schemas.payloads import (
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MarkPayload,
    MovePayload,
    SetVisibilityPayload,
)
from app.services.intents import IntentValidationError, validate_intent

from tests.actions.support import Seeded, attack, damage, heal, move, set_visibility

# --- host permissions -----------------------------------------------------------


async def test_host_may_move_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=move(seeded.token2_id),
        )
    assert isinstance(payload, MovePayload)
    assert payload.token_id == seeded.token2_id
    assert (payload.x, payload.y) == (5, 6)


async def test_host_may_damage_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=damage(seeded.token1_id, amount=7),
        )
    assert isinstance(payload, DamagePayload)
    assert payload.amount == 7


async def test_host_may_heal_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=heal(seeded.token2_id, amount=5),
        )
    assert isinstance(payload, HealPayload)
    assert payload.amount == 5


# --- player permissions ---------------------------------------------------------


async def test_player_may_move_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=move(seeded.token1_id),
        )
    assert isinstance(payload, MovePayload)
    assert payload.token_id == seeded.token1_id


async def test_player_may_damage_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=damage(seeded.token1_id),
        )
    assert isinstance(payload, DamagePayload)


async def test_player_may_heal_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=heal(seeded.token1_id),
        )
    assert isinstance(payload, HealPayload)


async def test_player_may_not_heal_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=heal(seeded.token2_id),
            )
    assert "your own token" in exc.value.reason


async def test_player_may_not_move_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=move(seeded.token2_id),
            )
    assert "your own token" in exc.value.reason


async def test_player_may_not_damage_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError):
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p2_character_id,
                intent=damage(seeded.token1_id),
            )


async def test_player_with_no_character_cannot_target_a_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError):
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=None,
                intent=move(seeded.token1_id),
            )


# --- attack permissions + resolution --------------------------------------------


async def test_host_may_attack_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=attack(seeded.token1_id, seeded.token2_id),
        )
    assert isinstance(payload, AttackIntentPayload)
    assert payload.attacker_token_id == seeded.token1_id
    assert payload.target_token_id == seeded.token2_id


async def test_player_may_attack_from_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=attack(seeded.token1_id, seeded.token2_id),
        )
    assert isinstance(payload, AttackIntentPayload)


async def test_player_cannot_attack_from_a_foreign_token(seeded: Seeded) -> None:
    """The attacker token must be the player's own; attacking WITH token2 is rejected."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=attack(seeded.token2_id, seeded.token1_id),
            )
    assert "your own token" in exc.value.reason


async def test_attack_target_must_be_on_this_board(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=attack(seeded.token1_id, seeded.other_room_token_id),
            )
    assert "not on this board" in exc.value.reason


# --- state bounds ---------------------------------------------------------------


async def test_unknown_token_is_rejected(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=move(uuid.uuid4()),
            )
    assert "not on this board" in exc.value.reason


async def test_token_from_another_room_is_rejected(seeded: Seeded) -> None:
    """Even the host of one room cannot act on a token belonging to a different room."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=move(seeded.other_room_token_id),
            )
    assert "not on this board" in exc.value.reason


# --- non-token actions ----------------------------------------------------------


async def test_player_may_mark(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=ActionIntent(payload=MarkPayload(x=3, y=3, label="here")),
        )
    assert isinstance(payload, MarkPayload)
    assert payload.label == "here"


async def _seat_initiative(seeded: Seeded, *, order: list[uuid.UUID], active_index: int) -> None:
    """Seat the given characters in ``seeded``'s room and set the active turn."""
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        for index, character_id in enumerate(order):
            session.add(
                InitiativeEntry(
                    room_id=seeded.room_id,
                    character_id=character_id,
                    name=f"C{index}",
                    initiative=20 - index,
                    order_index=index,
                )
            )
        room.initiative_active_index = active_index
        await session.commit()


async def test_host_may_always_end_turn(seeded: Seeded) -> None:
    """The host may advance the order even before combat has started."""
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=ActionIntent(payload=EndTurnPayload()),
        )
    assert isinstance(payload, EndTurnPayload)


async def test_player_cannot_end_turn_before_combat(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=ActionIntent(payload=EndTurnPayload()),
            )
    assert "Combat has not started" in exc.value.reason


async def test_player_may_end_their_own_turn(seeded: Seeded) -> None:
    await _seat_initiative(
        seeded, order=[seeded.p1_character_id, seeded.p2_character_id], active_index=0
    )
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=ActionIntent(payload=EndTurnPayload()),
        )
    assert isinstance(payload, EndTurnPayload)


async def test_player_cannot_end_another_combatants_turn(seeded: Seeded) -> None:
    await _seat_initiative(
        seeded, order=[seeded.p1_character_id, seeded.p2_character_id], active_index=0
    )
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p2_character_id,
                intent=ActionIntent(payload=EndTurnPayload()),
            )
    assert "not your turn" in exc.value.reason


# --- fog of war: hidden tokens (host-only) ---------------------------------------


async def test_host_may_set_token_visibility(seeded: Seeded) -> None:
    """The host may hide/reveal any token in their room (fog of war)."""
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=set_visibility(seeded.token2_id, hidden=True),
        )
    assert isinstance(payload, SetVisibilityPayload)
    assert payload.token_id == seeded.token2_id
    assert payload.hidden is True


async def test_player_cannot_set_token_visibility(seeded: Seeded) -> None:
    """A player may NOT hide/reveal tokens — even their own (CLAUDE.md rule 3)."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=set_visibility(seeded.token1_id, hidden=True),
            )
    assert "host" in exc.value.reason.lower()


async def test_set_visibility_unknown_token_is_rejected(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=set_visibility(uuid.uuid4(), hidden=True),
            )
    assert "not on this board" in exc.value.reason
