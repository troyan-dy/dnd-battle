"""Unit tests for the Phase 1 ORM data model.

Run against an in-memory sqlite database (StaticPool keeps the single connection
alive across sessions) so no Postgres is required. Verifies schema creation,
relationships, enum round-trips, JSON defaults, and the InviteLink security
invariant that ``token_hash`` is unique.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.models import (
    Base,
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    RoomStatus,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to a fresh in-memory schema."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def test_full_graph_persists_and_relationships_load(session: AsyncSession) -> None:
    """A room with a character, participant and invite link round-trips intact."""
    room = Room(name="Goblin Ambush")
    character = Character(room=room, name="Aria", max_hp=24, current_hp=24)
    player = Participant(
        room=room,
        role=ParticipantRole.player,
        display_name="Bob",
        character=character,
    )
    link = InviteLink(
        room=room,
        participant=player,
        token_hash=_hash(secrets.token_urlsafe(32)),
    )
    session.add(room)
    await session.commit()

    fetched = await session.get(Room, room.id)
    assert fetched is not None
    # Server-managed defaults.
    assert fetched.status is RoomStatus.lobby
    assert fetched.created_at is not None
    assert len(fetched.participants) == 1
    assert len(fetched.characters) == 1
    assert len(fetched.invite_links) == 1

    fetched_player = fetched.participants[0]
    assert fetched_player.role is ParticipantRole.player
    assert fetched_player.character is not None
    assert fetched_player.character.name == "Aria"
    assert fetched_player.invite_links[0].id == link.id


async def test_character_json_columns_default_empty(session: AsyncSession) -> None:
    """ability_scores defaults to an empty dict and conditions to an empty list."""
    room = Room(name="Test")
    character = Character(room=room, name="Mob", max_hp=10, current_hp=10)
    session.add(room)
    await session.commit()
    await session.refresh(character)

    assert character.ability_scores == {}
    assert character.conditions == []


async def test_invite_link_token_hash_is_unique(session: AsyncSession) -> None:
    """Two invite links may not share a token hash (security invariant)."""
    room = Room(name="Dup")
    p1 = Participant(room=room, role=ParticipantRole.player)
    p2 = Participant(room=room, role=ParticipantRole.player)
    digest = _hash("same-token")
    session.add_all(
        [
            room,
            InviteLink(room=room, participant=p1, token_hash=digest),
            InviteLink(room=room, participant=p2, token_hash=digest),
        ]
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_invite_link_revocation_columns_default_null(session: AsyncSession) -> None:
    """A freshly created link is active: no revoked_at / used_at / expires_at."""
    room = Room(name="Live")
    participant = Participant(room=room, role=ParticipantRole.host)
    link = InviteLink(room=room, participant=participant, token_hash=_hash("tok"))
    session.add(room)
    await session.commit()
    await session.refresh(link)

    assert link.revoked_at is None
    assert link.used_at is None
    assert link.expires_at is None
