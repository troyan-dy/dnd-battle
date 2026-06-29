"""Unit tests for the shared service layer (invite resolution + BoardState build).

These run against an in-memory sqlite schema and target the service functions
directly, so the same logic the realtime ``join`` relies on is covered apart from
the transport.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest_asyncio
from app.models import (
    Base,
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.security.tokens import generate_token, hash_token
from app.services.board import build_board_state
from app.services.invites import is_invite_active, resolve_active_invite
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


# --- resolve_active_invite ------------------------------------------------------


async def test_resolve_active_invite_returns_binding(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    token = generate_token()
    async with factory() as session:
        room = Room(name="R")
        session.add(room)
        await session.flush()
        character = Character(room_id=room.id, name="Aria", max_hp=10, current_hp=10)
        session.add(character)
        await session.flush()
        player = Participant(
            room_id=room.id, role=ParticipantRole.player, character_id=character.id
        )
        session.add(player)
        await session.flush()
        session.add(
            InviteLink(room_id=room.id, participant_id=player.id, token_hash=hash_token(token))
        )
        await session.commit()
        room_id, participant_id, character_id = room.id, player.id, character.id

    async with factory() as session:
        resolved = await resolve_active_invite(session, token)

    assert resolved is not None
    assert resolved.room_id == room_id
    assert resolved.participant_id == participant_id
    assert resolved.role == ParticipantRole.player
    assert resolved.character_id == character_id


async def test_resolve_active_invite_unknown_and_blank(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        assert await resolve_active_invite(session, "nope") is None
        assert await resolve_active_invite(session, "") is None


async def test_resolve_active_invite_revoked_and_expired(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    revoked_token = generate_token()
    expired_token = generate_token()
    async with factory() as session:
        room = Room(name="R")
        session.add(room)
        await session.flush()
        host = Participant(room_id=room.id, role=ParticipantRole.host)
        session.add(host)
        await session.flush()
        session.add_all(
            [
                InviteLink(
                    room_id=room.id,
                    participant_id=host.id,
                    token_hash=hash_token(revoked_token),
                    revoked_at=dt.datetime.now(dt.UTC),
                ),
                InviteLink(
                    room_id=room.id,
                    participant_id=host.id,
                    token_hash=hash_token(expired_token),
                    expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()

    async with factory() as session:
        assert await resolve_active_invite(session, revoked_token) is None
        assert await resolve_active_invite(session, expired_token) is None


def test_is_invite_active_naive_expiry_treated_as_utc() -> None:
    """A tz-naive expires_at in the future is treated as UTC and stays active."""
    now = dt.datetime.now(dt.UTC)
    link = InviteLink(
        token_hash="x",
        expires_at=(now + dt.timedelta(hours=1)).replace(tzinfo=None),
    )
    assert is_invite_active(link, now) is True


# --- build_board_state ----------------------------------------------------------


async def test_build_board_state_empty_room(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        room = Room(name="Empty")
        session.add(room)
        await session.commit()
        room_id = room.id

    async with factory() as session:
        board = await build_board_state(session, room_id)

    assert board.room_id == room_id
    assert board.tokens == []
    assert board.characters == []


async def test_build_board_state_includes_tokens_and_characters(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        room = Room(name="R")
        session.add(room)
        await session.flush()
        character = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=18)
        session.add(character)
        await session.flush()
        session.add(Token(room_id=room.id, character_id=character.id, x=2, y=5, size=2))
        await session.commit()
        room_id, character_id = room.id, character.id

    async with factory() as session:
        board = await build_board_state(session, room_id)

    assert len(board.tokens) == 1
    assert board.tokens[0].character_id == character_id
    assert board.tokens[0].x == 2
    assert board.tokens[0].y == 5
    assert board.tokens[0].size == 2
    assert len(board.characters) == 1
    assert board.characters[0].name == "Aria"
    assert board.characters[0].current_hp == 18


async def test_build_board_state_isolates_other_rooms(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Only the requested room's tokens/characters are included."""
    async with factory() as session:
        room_a = Room(name="A")
        room_b = Room(name="B")
        session.add_all([room_a, room_b])
        await session.flush()
        char_b = Character(room_id=room_b.id, name="Other", max_hp=5, current_hp=5)
        session.add(char_b)
        await session.flush()
        session.add(Token(room_id=room_b.id, character_id=char_b.id, x=0, y=0, size=1))
        await session.commit()
        room_a_id = room_a.id

    async with factory() as session:
        board = await build_board_state(session, room_a_id)

    assert board.tokens == []
    assert board.characters == []
