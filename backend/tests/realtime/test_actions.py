"""Tests of the realtime ``action`` event: validate, apply and broadcast intents."""

from __future__ import annotations

import random
import uuid

from app.models import (
    Character,
    InitiativeEntry,
    ParticipantRole,
    Room,
    Token,
)
from app.realtime.actions import handle_action
from app.realtime.connection import JoinedIdentity
from app.realtime.rooms import room_name
from app.realtime.sequence import RoomSequencer

from tests.realtime.support import (
    SeededBoard,
    fake_sio,
    joined,
    move_intent,
    seeded_token_id,
)


async def test_handle_action_rejects_when_not_joined() -> None:
    """An action on a connection that never joined is acked-error and not broadcast."""
    sio = fake_sio()  # default get_session -> {} (no identity)

    ack = await handle_action(
        sio, "sid1", move_intent(uuid.uuid4(), 1, 1), sequencer=RoomSequencer()
    )

    assert ack["ok"] is False
    assert "error" in ack
    # The only emit is the error to the caller; nothing broadcast to a room.
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


async def test_handle_action_rejects_malformed_intent(seeded: SeededBoard) -> None:
    """A bad protocol version fails to parse -> error ack, no broadcast, no mutation."""
    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    token_id = await seeded_token_id(seeded)
    bad = {
        "version": 999,
        "payload": {"type": "move", "token_id": str(token_id), "x": 1, "y": 1},
    }

    ack = await handle_action(
        sio, "sid1", bad, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is False
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


async def test_handle_action_host_move_broadcasts_and_persists(seeded: SeededBoard) -> None:
    """A host move broadcasts the stamped Action to the room AND moves the token row."""
    sio = fake_sio()
    actor = uuid.uuid4()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=actor,
            character_id=None,
        ),
    )
    token_id = await seeded_token_id(seeded)

    ack = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 7, 8),
        sequencer=RoomSequencer(),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is True
    assert ack["seq"] == 0

    # Broadcast to the whole room (not `to=` a single sid).
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    assert kwargs == {"room": room_name(str(seeded.room_id))}
    action = args[1]
    assert action["room_id"] == str(seeded.room_id)
    assert action["actor_participant_id"] == str(actor)
    assert action["seq"] == 0
    assert action["payload"] == {
        "type": "move",
        "token_id": str(token_id),
        "x": 7,
        "y": 8,
    }

    # Durable row reflects the move (reconnect-safe).
    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert (token.x, token.y) == (7, 8)


async def test_handle_action_player_end_turn_advances_and_broadcasts(
    seeded: SeededBoard,
) -> None:
    """A player ending their own turn advances the initiative pointer + broadcasts."""
    # Seat the player's character first, then an NPC; the player is active (seat 0).
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        session.add_all(
            [
                InitiativeEntry(
                    room_id=seeded.room_id,
                    character_id=seeded.player_character_id,
                    name="Aria",
                    initiative=18,
                    order_index=0,
                ),
                InitiativeEntry(
                    room_id=seeded.room_id,
                    character_id=None,
                    name="Goblin",
                    initiative=10,
                    order_index=1,
                ),
            ]
        )
        room.initiative_active_index = 0
        await session.commit()

    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=seeded.player_character_id,
        ),
    )

    ack = await handle_action(
        sio,
        "sid1",
        {"version": 1, "payload": {"type": "endTurn"}},
        sequencer=RoomSequencer(),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is True
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    assert kwargs == {"room": room_name(str(seeded.room_id))}
    assert args[1]["payload"] == {"type": "endTurn"}

    # The durable pointer advanced to the next seat (reconnect-safe).
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        assert room.initiative_active_index == 1


async def test_handle_action_player_end_turn_rejected_when_not_their_turn(
    seeded: SeededBoard,
) -> None:
    """A player cannot end a turn that is not theirs -> error ack, no broadcast."""
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        session.add(
            InitiativeEntry(
                room_id=seeded.room_id,
                character_id=None,
                name="Goblin",
                initiative=20,
                order_index=0,
            )
        )
        room.initiative_active_index = 0
        await session.commit()

    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=seeded.player_character_id,
        ),
    )

    ack = await handle_action(
        sio,
        "sid1",
        {"version": 1, "payload": {"type": "endTurn"}},
        sequencer=RoomSequencer(),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is False
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}

    # Pointer is unchanged (no broadcast, no mutation).
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        assert room.initiative_active_index == 0


async def test_handle_action_player_damage_persists_clamped(seeded: SeededBoard) -> None:
    """A player damaging their own token reduces HP (clamped at 0) and broadcasts."""
    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=seeded.player_character_id,
        ),
    )
    token_id = await seeded_token_id(seeded)
    intent = {
        "version": 1,
        "payload": {"type": "damage", "token_id": str(token_id), "amount": 1000},
    }

    ack = await handle_action(
        sio, "sid1", intent, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is True
    args, _ = sio.emit.await_args
    assert args[0] == "action"

    async with seeded.factory() as session:
        character = await session.get(Character, seeded.player_character_id)
        assert character is not None
        assert character.current_hp == 0  # 20 - 1000, clamped


async def test_handle_action_host_heal_persists_clamped(seeded: SeededBoard) -> None:
    """A host healing a token restores HP (clamped at max_hp) and broadcasts."""
    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    token_id = await seeded_token_id(seeded)
    intent = {
        "version": 1,
        "payload": {"type": "heal", "token_id": str(token_id), "amount": 100},
    }

    ack = await handle_action(
        sio, "sid1", intent, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is True
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    assert kwargs == {"room": room_name(str(seeded.room_id))}
    assert args[1]["payload"] == {
        "type": "heal",
        "token_id": str(token_id),
        "amount": 100,
    }

    async with seeded.factory() as session:
        character = await session.get(Character, seeded.player_character_id)
        assert character is not None
        assert character.current_hp == 24  # 20 + 100, clamped at max_hp (24)


async def test_handle_action_player_cannot_move_foreign_token(seeded: SeededBoard) -> None:
    """A player whose character does not own the token is rejected, never broadcast."""
    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=uuid.uuid4(),  # not the token's character
        ),
    )
    token_id = await seeded_token_id(seeded)

    ack = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 1, 1),
        sequencer=RoomSequencer(),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is False
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}

    # Token unchanged (no durable mutation on a rejected action).
    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert (token.x, token.y) == (3, 4)


async def test_handle_action_player_mark_broadcasts_without_mutation(seeded: SeededBoard) -> None:
    """A player's mark/ping broadcasts to the WHOLE room and changes no durable rows.

    Marks are ephemeral (no Mark row, no BoardState field): the server validates the
    intent — a non-token payload any participant may issue — and broadcasts the stamped
    Action so everyone sees the ping, while apply_action is a deliberate no-op for it.
    """
    sio = fake_sio()
    actor = seeded.player_participant_id
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=actor,
            character_id=seeded.player_character_id,
        ),
    )
    token_id = await seeded_token_id(seeded)
    intent = {
        "version": 1,
        "payload": {"type": "mark", "x": 5, "y": 6, "color": "#ff0000", "label": "here"},
    }

    ack = await handle_action(
        sio, "sid1", intent, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is True
    # Broadcast to the whole room (everyone sees the ping), not a single sid.
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    assert kwargs == {"room": room_name(str(seeded.room_id))}
    action = args[1]
    assert action["actor_participant_id"] == str(actor)
    assert action["payload"] == {
        "type": "mark",
        "x": 5,
        "y": 6,
        "color": "#ff0000",
        "label": "here",
    }

    # No durable mutation: token cell and character HP are untouched.
    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert (token.x, token.y) == (3, 4)
        character = await session.get(Character, seeded.player_character_id)
        assert character is not None
        assert character.current_hp == 20


async def test_handle_action_host_attack_resolves_and_broadcasts(seeded: SeededBoard) -> None:
    """A host attack rolls server-side, applies the rolled damage, and broadcasts it.

    The roll is server-authoritative (CLAUDE.md rule 1): the client sends only the
    attacker/target + offence, the server rolls (deterministically here via a seeded
    rng), reduces the target character's durable HP by exactly the rolled damage, and
    broadcasts an `attack` result everyone can log.
    """
    sio = fake_sio()
    joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    token_id = await seeded_token_id(seeded)
    intent = {
        "version": 1,
        "payload": {
            "type": "attack",
            "attacker_token_id": str(token_id),
            "target_token_id": str(token_id),
            "attack_bonus": 3,
            "damage": "1d6",
        },
    }

    ack = await handle_action(
        sio,
        "sid1",
        intent,
        sequencer=RoomSequencer(),
        rng=random.Random(1),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is True
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    assert kwargs == {"room": room_name(str(seeded.room_id))}
    payload = args[1]["payload"]
    assert payload["type"] == "attack"
    assert 1 <= payload["attack_roll"] <= 20
    assert payload["attack_total"] == payload["attack_roll"] + 3
    damage_total = payload["damage_total"]
    assert damage_total >= 0

    # The target character's durable HP dropped by exactly the rolled damage.
    async with seeded.factory() as session:
        character = await session.get(Character, seeded.player_character_id)
        assert character is not None
        assert character.current_hp == max(0, 20 - damage_total)
