"""Tests for server-side Action intent validation (permissions + bounds).

Exercises ``app.services.actions.validate_intent`` against a seeded in-memory
database: host can target any token in its room, a player only its own token,
cross-owner / cross-room / unknown tokens are rejected, and non-token actions
(mark, endTurn) are allowed for any authenticated participant.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.models import Base, Character, Participant, ParticipantRole, Room, Token
from app.schemas.action import (
    ActionIntent,
    DamagePayload,
    EndTurnPayload,
    MarkPayload,
    MovePayload,
)
from app.services.actions import IntentValidationError, validate_intent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@dataclass
class Seeded:
    factory: async_sessionmaker[AsyncSession]
    room_id: uuid.UUID
    # Player 1: owns char1 / token1
    p1_character_id: uuid.UUID
    token1_id: uuid.UUID
    # Player 2: owns char2 / token2
    p2_character_id: uuid.UUID
    token2_id: uuid.UUID
    # A token in a DIFFERENT room
    other_room_token_id: uuid.UUID


@pytest_asyncio.fixture
async def seeded() -> AsyncIterator[Seeded]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with factory() as session:
        room = Room(name="Goblin Ambush")
        other_room = Room(name="Other")
        session.add_all([room, other_room])
        await session.flush()

        char1 = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=24)
        char2 = Character(room_id=room.id, name="Borin", max_hp=30, current_hp=30)
        other_char = Character(room_id=other_room.id, name="Stranger", max_hp=10, current_hp=10)
        session.add_all([char1, char2, other_char])
        await session.flush()

        session.add_all(
            [
                Participant(room_id=room.id, role=ParticipantRole.host, display_name="DM"),
                Participant(
                    room_id=room.id,
                    role=ParticipantRole.player,
                    character_id=char1.id,
                ),
                Participant(
                    room_id=room.id,
                    role=ParticipantRole.player,
                    character_id=char2.id,
                ),
            ]
        )
        token1 = Token(room_id=room.id, character_id=char1.id, x=1, y=1, size=1)
        token2 = Token(room_id=room.id, character_id=char2.id, x=2, y=2, size=1)
        other_token = Token(room_id=other_room.id, character_id=other_char.id, x=0, y=0, size=1)
        session.add_all([token1, token2, other_token])
        await session.commit()

        seeded = Seeded(
            factory=factory,
            room_id=room.id,
            p1_character_id=char1.id,
            token1_id=token1.id,
            p2_character_id=char2.id,
            token2_id=token2.id,
            other_room_token_id=other_token.id,
        )

    yield seeded
    await engine.dispose()


def _move(token_id: uuid.UUID, x: int = 5, y: int = 6) -> ActionIntent:
    return ActionIntent(payload=MovePayload(token_id=token_id, x=x, y=y))


def _damage(token_id: uuid.UUID, amount: int = 3) -> ActionIntent:
    return ActionIntent(payload=DamagePayload(token_id=token_id, amount=amount))


# --- host permissions -----------------------------------------------------------


async def test_host_may_move_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_move(seeded.token2_id),
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
            intent=_damage(seeded.token1_id, amount=7),
        )
    assert isinstance(payload, DamagePayload)
    assert payload.amount == 7


# --- player permissions ---------------------------------------------------------


async def test_player_may_move_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=_move(seeded.token1_id),
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
            intent=_damage(seeded.token1_id),
        )
    assert isinstance(payload, DamagePayload)


async def test_player_may_not_move_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=_move(seeded.token2_id),
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
                intent=_damage(seeded.token1_id),
            )


async def test_player_with_no_character_cannot_target_a_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError):
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=None,
                intent=_move(seeded.token1_id),
            )


# --- state bounds ---------------------------------------------------------------


async def test_unknown_token_is_rejected(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=_move(uuid.uuid4()),
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
                intent=_move(seeded.other_room_token_id),
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


async def test_any_participant_may_end_turn(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=ActionIntent(payload=EndTurnPayload()),
        )
    assert isinstance(payload, EndTurnPayload)
