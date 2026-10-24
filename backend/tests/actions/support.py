"""Shared fixtures data + intent builders for the action-service tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models import (
    Character,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.schemas.action import ActionIntent
from app.schemas.attack import AttackIntentPayload
from app.schemas.payloads import (
    DamagePayload,
    HealPayload,
    MovePayload,
    SetVisibilityPayload,
)

from tests.support import SessionMaker


@dataclass
class Seeded:
    factory: SessionMaker
    room_id: uuid.UUID
    # Player 1: owns char1 / token1
    p1_character_id: uuid.UUID
    token1_id: uuid.UUID
    # Player 2: owns char2 / token2
    p2_character_id: uuid.UUID
    token2_id: uuid.UUID
    # A token in a DIFFERENT room
    other_room_token_id: uuid.UUID


async def seed_actions_board(factory: SessionMaker) -> Seeded:
    """Seed two rooms: two player tokens in one, a stray token in the other."""
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
        token1 = Token(
            room_id=room.id,
            character_id=char1.id,
            x=1,
            y=1,
            size=1,
        )
        token2 = Token(
            room_id=room.id,
            character_id=char2.id,
            x=2,
            y=2,
            size=1,
        )
        other_token = Token(
            room_id=other_room.id,
            character_id=other_char.id,
            x=0,
            y=0,
            size=1,
        )
        session.add_all([token1, token2, other_token])
        await session.commit()

    return Seeded(
        factory=factory,
        room_id=room.id,
        p1_character_id=char1.id,
        token1_id=token1.id,
        p2_character_id=char2.id,
        token2_id=token2.id,
        other_room_token_id=other_token.id,
    )


def move(token_id: uuid.UUID, column: int = 5, row: int = 6) -> ActionIntent:
    return ActionIntent(payload=MovePayload(token_id=token_id, x=column, y=row))


def damage(token_id: uuid.UUID, amount: int = 3) -> ActionIntent:
    return ActionIntent(payload=DamagePayload(token_id=token_id, amount=amount))


def heal(token_id: uuid.UUID, amount: int = 3) -> ActionIntent:
    return ActionIntent(payload=HealPayload(token_id=token_id, amount=amount))


def attack(
    attacker: uuid.UUID,
    target: uuid.UUID,
    *,
    damage: str = "1d6",
    damage_type: str = "slashing",
) -> ActionIntent:
    return ActionIntent(
        payload=AttackIntentPayload(
            attacker_token_id=attacker,
            target_token_id=target,
            damage=damage,
            damage_type=damage_type,  # type: ignore[arg-type]
        )
    )


def set_visibility(token_id: uuid.UUID, hidden: bool) -> ActionIntent:
    return ActionIntent(payload=SetVisibilityPayload(token_id=token_id, hidden=hidden))
