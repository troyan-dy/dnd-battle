"""Shared helpers for the realtime transport tests: a fake server + a seeded board."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from app.models import (
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.realtime.connection import JoinedIdentity
from app.security.tokens import generate_token, hash_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support import SessionMaker


def fake_sio() -> MagicMock:
    """A stand-in Socket.IO server with awaitable enter_room/emit/session spies."""
    sio = MagicMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    sio.save_session = AsyncMock()
    # Default: no identity bound (overridden per-test for joined connections).
    sio.get_session = AsyncMock(return_value={})
    return sio


@dataclass(frozen=True)
class SeededBoard:
    """Handles to a seeded room: tokens to render + the participants' invite tokens."""

    factory: SessionMaker
    room_id: uuid.UUID
    host_token: str
    player_token: str
    player_participant_id: uuid.UUID
    player_character_id: uuid.UUID


async def _seed_room_with_character(session: AsyncSession) -> tuple[Room, Character]:
    """Insert the seeded room and its single character (ids assigned)."""
    room = Room(name="Goblin Ambush")
    session.add(room)
    await session.flush()

    character = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=20)
    session.add(character)
    await session.flush()
    return room, character


async def seed_board(factory: SessionMaker) -> SeededBoard:
    """A room with a host link, a player (character + token), and a player link."""
    host_token = generate_token()
    player_token = generate_token()

    async with factory() as session:
        room, character = await _seed_room_with_character(session)

        host = Participant(room_id=room.id, role=ParticipantRole.host, display_name="DM")
        player = Participant(
            room_id=room.id,
            role=ParticipantRole.player,
            display_name="P1",
            character_id=character.id,
        )
        session.add_all([host, player])
        await session.flush()

        session.add_all(
            [
                InviteLink(
                    room_id=room.id, participant_id=host.id, token_hash=hash_token(host_token)
                ),
                InviteLink(
                    room_id=room.id,
                    participant_id=player.id,
                    token_hash=hash_token(player_token),
                ),
                Token(room_id=room.id, character_id=character.id, x=3, y=4, size=1),
            ]
        )
        await session.commit()

    return SeededBoard(
        factory=factory,
        room_id=room.id,
        host_token=host_token,
        player_token=player_token,
        player_participant_id=player.id,
        player_character_id=character.id,
    )


def joined(sio: MagicMock, identity: JoinedIdentity) -> None:
    """Bind an authenticated identity to the fake connection (as join would)."""
    sio.get_session = AsyncMock(return_value=identity)


async def seeded_token_id(seeded: SeededBoard) -> uuid.UUID:
    async with seeded.factory() as session:
        token = (await session.execute(select(Token))).scalar_one()
        return token.id


def move_intent(token_id: uuid.UUID, column: int, row: int) -> dict[str, object]:
    return {
        "version": 1,
        "payload": {"type": "move", "token_id": str(token_id), "x": column, "y": row},
    }
