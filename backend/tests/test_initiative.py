"""Tests for the initiative / turn-order service (set, advance, build).

Exercises ``app.services.initiative`` against a seeded in-memory database: setting
the order sorts by initiative descending and resets the active turn; ``endTurn``
advancing wraps and bumps the round; the built snapshot is reconnect-safe.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from app.models import Base, Character, Room
from app.schemas.room import InitiativeEntryInput
from app.services.initiative import (
    active_character_id,
    advance_turn,
    build_initiative_state,
    set_initiative,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _make_room(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a room with two characters; return (room_id, char_a_id, char_b_id)."""
    async with factory() as session:
        room = Room(name="Encounter")
        session.add(room)
        await session.flush()
        char_a = Character(room_id=room.id, name="Aria", max_hp=20, current_hp=20)
        char_b = Character(room_id=room.id, name="Borin", max_hp=20, current_hp=20)
        session.add_all([char_a, char_b])
        await session.commit()
        return room.id, char_a.id, char_b.id


async def test_set_initiative_sorts_desc_and_resets_active(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, char_a, char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        state = await set_initiative(
            session,
            room=room,
            entries=[
                InitiativeEntryInput(character_id=char_a, name="Aria", initiative=12),
                InitiativeEntryInput(character_id=char_b, name="Borin", initiative=18),
            ],
        )
        await session.commit()

    # Borin (18) sorts ahead of Aria (12); active turn resets to seat 0, round 1.
    assert [e.name for e in state.entries] == ["Borin", "Aria"]
    assert [e.order_index for e in state.entries] == [0, 1]
    assert state.active_index == 0
    assert state.round == 1


async def test_set_initiative_empty_clears_active(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, _char_a, _char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        state = await set_initiative(session, room=room, entries=[])
        await session.commit()
    assert state.entries == []
    assert state.active_index is None
    assert state.round == 1


async def test_set_initiative_replaces_previous_order(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, char_a, char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        await set_initiative(
            session,
            room=room,
            entries=[InitiativeEntryInput(character_id=char_a, name="Aria", initiative=10)],
        )
        await session.commit()
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        state = await set_initiative(
            session,
            room=room,
            entries=[InitiativeEntryInput(character_id=char_b, name="Borin", initiative=15)],
        )
        await session.commit()
    assert len(state.entries) == 1
    assert state.entries[0].name == "Borin"


async def test_advance_turn_moves_to_next_seat(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, char_a, char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        await set_initiative(
            session,
            room=room,
            entries=[
                InitiativeEntryInput(character_id=char_a, name="A", initiative=20),
                InitiativeEntryInput(character_id=char_b, name="B", initiative=10),
            ],
        )
        await advance_turn(session, room=room)
        await session.commit()
        assert room.initiative_active_index == 1
        assert room.initiative_round == 1


async def test_advance_turn_wraps_and_bumps_round(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, char_a, char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        await set_initiative(
            session,
            room=room,
            entries=[
                InitiativeEntryInput(character_id=char_a, name="A", initiative=20),
                InitiativeEntryInput(character_id=char_b, name="B", initiative=10),
            ],
        )
        await advance_turn(session, room=room)  # -> seat 1
        await advance_turn(session, room=room)  # wraps -> seat 0, round 2
        await session.commit()
        assert room.initiative_active_index == 0
        assert room.initiative_round == 2


async def test_advance_turn_noop_without_order(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, _char_a, _char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        await advance_turn(session, room=room)
        await session.commit()
        assert room.initiative_active_index is None
        assert room.initiative_round == 1


async def test_active_character_id_tracks_pointer(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, char_a, char_b = await _make_room(factory)
    async with factory() as session:
        room = await session.get(Room, room_id)
        assert room is not None
        await set_initiative(
            session,
            room=room,
            entries=[
                InitiativeEntryInput(character_id=char_a, name="A", initiative=20),
                InitiativeEntryInput(character_id=char_b, name="B", initiative=10),
            ],
        )
        await session.commit()
        assert await active_character_id(session, room) == char_a
        await advance_turn(session, room=room)
        assert await active_character_id(session, room) == char_b


async def test_build_initiative_state_empty_room(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    room_id, _char_a, _char_b = await _make_room(factory)
    async with factory() as session:
        state = await build_initiative_state(session, room_id)
    assert state.entries == []
    assert state.active_index is None
    assert state.round == 1
