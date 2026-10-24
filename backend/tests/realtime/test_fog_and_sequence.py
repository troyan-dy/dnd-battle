"""Realtime fog of war, per-room ``seq`` durability and reconnect resync tests."""

from __future__ import annotations

import uuid

from app.models import (
    ParticipantRole,
    Room,
    Token,
)
from app.realtime.actions import handle_action
from app.realtime.connection import JoinedIdentity
from app.realtime.join import handle_join
from app.realtime.rooms import host_room_name, player_room_name
from app.realtime.sequence import RoomSequencer
from sqlalchemy import select

from tests.realtime.support import (
    SeededBoard,
    fake_sio,
    joined,
    move_intent,
    seeded_token_id,
)

# --- fog of war ------------------------------------------------------------------


async def test_handle_action_host_set_visibility_resyncs_role_filtered_boards(
    seeded: SeededBoard,
) -> None:
    """Hiding a token flips its durable flag and resyncs each role with a filtered board.

    A visibility change is NOT rebroadcast as an Action (that would leak board info):
    the host gets the FULL board (hidden token present, flagged); players get a board
    with the hidden token stripped entirely (CLAUDE.md rule 3, server-enforced).
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
        "payload": {"type": "setVisibility", "token_id": str(token_id), "hidden": True},
    }

    ack = await handle_action(
        sio, "sid1", intent, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is True
    # Exactly two role-filtered boardState pushes — no `action` broadcast.
    calls = sio.emit.await_args_list
    assert len(calls) == 2
    by_room: dict[str, dict[str, object]] = {}
    for call in calls:
        name, payload = call.args
        assert name == "boardState"
        by_room[call.kwargs["room"]] = payload

    host_board = by_room[host_room_name(str(seeded.room_id))]
    player_board = by_room[player_room_name(str(seeded.room_id))]
    host_tokens = host_board["tokens"]
    player_tokens = player_board["tokens"]
    assert isinstance(host_tokens, list)
    assert isinstance(player_tokens, list)
    # Host still sees the token (now flagged hidden); the player no longer sees it.
    hidden_ids = {token["id"] for token in host_tokens if token["hidden"]}
    assert str(token_id) in hidden_ids
    assert all(token["id"] != str(token_id) for token in player_tokens)

    # The durable hidden flag persisted (reconnect-safe).
    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert token.hidden is True


async def test_handle_action_player_cannot_set_visibility(seeded: SeededBoard) -> None:
    """A player's setVisibility is rejected and changes no durable flag (host-only)."""
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
        "payload": {"type": "setVisibility", "token_id": str(token_id), "hidden": True},
    }

    ack = await handle_action(
        sio, "sid1", intent, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is False
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}

    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert token.hidden is False


async def test_handle_action_move_of_hidden_token_broadcasts_to_hosts_only(
    seeded: SeededBoard,
) -> None:
    """Moving an already-hidden token broadcasts to HOSTS only — never to players."""
    async with seeded.factory() as session:
        token = (await session.execute(select(Token))).scalar_one()
        token.hidden = True
        await session.commit()

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

    ack = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 7, 8),
        sequencer=RoomSequencer(),
        session_factory=seeded.factory,
    )

    assert ack["ok"] is True
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "action"
    # Targeted at the host sub-room, NOT the base room (players never see it move).
    assert kwargs == {"room": host_room_name(str(seeded.room_id))}
    assert args[1]["payload"]["type"] == "move"

    # The move still persisted durably (a reconnecting host rebuilds it).
    async with seeded.factory() as session:
        moved = await session.get(Token, token_id)
        assert moved is not None
        assert (moved.x, moved.y) == (7, 8)


async def test_handle_action_seq_is_monotonic_per_room(seeded: SeededBoard) -> None:
    """A shared sequencer hands out increasing seq across actions in the same room."""
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
    sequencer = RoomSequencer()

    ack1 = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 1, 1),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )
    ack2 = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 2, 2),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )

    assert ack1["seq"] == 0
    assert ack2["seq"] == 1


async def test_handle_action_persists_seq_high_water_on_room(seeded: SeededBoard) -> None:
    """Each broadcast bumps the durable Room.last_action_seq (next seq to issue)."""
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
    sequencer = RoomSequencer()

    await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 1, 1),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )
    await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 2, 2),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )

    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        # Two actions issued seq 0 and 1; the next seq to issue is persisted as 2.
        assert room.last_action_seq == 2


async def test_action_seq_survives_server_restart(seeded: SeededBoard) -> None:
    """A fresh sequencer (a restarted process) resumes seq from the persisted value.

    Proves the action sequence is durable (CLAUDE.md rule 2): the first process issues
    seq 0 and 1, persisting the high-water on the Room row. A brand-new RoomSequencer
    with an EMPTY in-memory cache — modelling a server restart — must seed from that
    durable value and hand out 2 next, never colliding back at 0 (which would break
    client ordering / de-duplication of broadcasts).
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

    # First process: two actions through one sequencer.
    first_process = RoomSequencer()
    ack0 = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 1, 1),
        sequencer=first_process,
        session_factory=seeded.factory,
    )
    ack1 = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 2, 2),
        sequencer=first_process,
        session_factory=seeded.factory,
    )
    assert ack0["seq"] == 0
    assert ack1["seq"] == 1

    # Server restarts: a brand-new sequencer with no in-memory state.
    restarted_process = RoomSequencer()
    ack2 = await handle_action(
        sio,
        "sid1",
        move_intent(token_id, 3, 3),
        sequencer=restarted_process,
        session_factory=seeded.factory,
    )
    # Resumes from the persisted high-water rather than restarting at 0.
    assert ack2["seq"] == 2

    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        assert room.last_action_seq == 3


async def test_reload_player_link_mid_encounter_restores_state(seeded: SeededBoard) -> None:
    """Reloading a player link mid-encounter resyncs the FULL post-action board.

    Models a player who joins, sees the board, then RELOADS its link (a brand-new
    connection) after the host has moved a token AND damaged the character. The fresh
    join must push the UPDATED authoritative BoardState — the moved token cell and the
    reduced HP — proving reconnect-safe restore (CLAUDE.md rule 2): the reconnecting
    client never has to have seen the intervening Actions, the durable rows are the
    source of truth and the snapshot is rebuilt on every (re)join.
    """
    sequencer = RoomSequencer()
    token_id = await seeded_token_id(seeded)

    # 1. Player joins initially and sees the token at its starting cell.
    player_sio = fake_sio()
    first_ack = await handle_join(
        player_sio, "p-sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )
    assert first_ack["ok"] is True
    args, _ = player_sio.emit.await_args
    assert args[0] == "boardState"
    pushed_token = args[1]["tokens"][0]
    assert (pushed_token["x"], pushed_token["y"]) == (3, 4)
    assert args[1]["characters"][0]["current_hp"] == 20

    # 2. Host moves the token AND damages the character mid-encounter
    #    (durable apply + broadcast on each).
    host_sio = fake_sio()
    joined(
        host_sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    move_ack = await handle_action(
        host_sio,
        "h-sid1",
        move_intent(token_id, 7, 8),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )
    damage_ack = await handle_action(
        host_sio,
        "h-sid1",
        {"version": 1, "payload": {"type": "damage", "token_id": str(token_id), "amount": 5}},
        sequencer=sequencer,
        session_factory=seeded.factory,
    )
    assert move_ack["ok"] is True
    assert damage_ack["ok"] is True

    # 3. The player reloads its link on a fresh connection (simulated reconnect).
    reconnect_sio = fake_sio()
    ack = await handle_join(
        reconnect_sio, "p-sid2", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["roomId"] == str(seeded.room_id)
    assert ack["participantId"] == str(seeded.player_participant_id)

    # The fresh boardState reflects the mid-encounter changes, not the stale start.
    reconnect_sio.emit.assert_awaited_once()
    args, kwargs = reconnect_sio.emit.await_args
    assert args[0] == "boardState"
    assert kwargs == {"to": "p-sid2"}
    board = args[1]
    assert len(board["tokens"]) == 1
    restored_token = board["tokens"][0]
    assert (restored_token["x"], restored_token["y"]) == (7, 8)
    assert board["characters"][0]["current_hp"] == 15  # 20 - 5

    # Identity is re-bound on reconnect so the player can keep acting after reload.
    reconnect_sio.save_session.assert_awaited_once()
    identity = reconnect_sio.save_session.await_args.args[1]
    assert isinstance(identity, JoinedIdentity)
    assert identity.participant_id == seeded.player_participant_id
