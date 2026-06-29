"""Tests for the Socket.IO realtime transport (mount + authenticated join).

Three layers:
- Unit tests drive the handler functions with a fake AsyncServer (AsyncMock) so the
  connection lifecycle + join failure paths are verified without a network.
- DB-backed join tests inject a session_factory bound to an in-memory sqlite schema
  so the token-authenticated join + FULL BoardState push is exercised end to end.
- An integration test drives the combined ASGI app via httpx to prove the REST API
  still works (FastAPI passthrough) AND the Socket.IO handshake is served, i.e. the
  server is genuinely mounted on FastAPI.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
import socketio
from app.main import create_app
from app.models import (
    Base,
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.realtime import create_asgi_app, create_sio_server
from app.realtime.events import (
    ROOM_PREFIX,
    JoinedIdentity,
    handle_action,
    handle_connect,
    handle_disconnect,
    handle_join,
    register_handlers,
    room_name,
)
from app.realtime.sequence import RoomSequencer
from app.security.tokens import generate_token, hash_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def _fake_sio() -> MagicMock:
    """A stand-in Socket.IO server with awaitable enter_room/emit/session spies."""
    sio = MagicMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    sio.save_session = AsyncMock()
    # Default: no identity bound (overridden per-test for joined connections).
    sio.get_session = AsyncMock(return_value={})
    return sio


# --- seeded in-memory DB --------------------------------------------------------


class SeededBoard:
    """Handles to a seeded room: tokens to render + the participants' invite tokens."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        room_id: uuid.UUID,
        host_token: str,
        player_token: str,
        player_participant_id: uuid.UUID,
        player_character_id: uuid.UUID,
    ) -> None:
        self.factory = factory
        self.room_id = room_id
        self.host_token = host_token
        self.player_token = player_token
        self.player_participant_id = player_participant_id
        self.player_character_id = player_character_id


@pytest_asyncio.fixture
async def seeded() -> AsyncIterator[SeededBoard]:
    """A room with a host link, a player (character + token), and a player link."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    host_token = generate_token()
    player_token = generate_token()

    async with factory() as session:
        room = Room(name="Goblin Ambush")
        session.add(room)
        await session.flush()

        character = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=20)
        session.add(character)
        await session.flush()

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

        board = SeededBoard(
            factory=factory,
            room_id=room.id,
            host_token=host_token,
            player_token=player_token,
            player_participant_id=player.id,
            player_character_id=character.id,
        )

    yield board
    await engine.dispose()


# --- transport unit tests -------------------------------------------------------


def test_room_name_is_prefixed() -> None:
    assert room_name("abc-123") == f"{ROOM_PREFIX}abc-123"


async def test_handle_connect_accepts() -> None:
    sio = _fake_sio()
    assert await handle_connect(sio, "sid1", {}, None) is True


async def test_handle_disconnect_is_noop() -> None:
    sio = _fake_sio()
    await handle_disconnect(sio, "sid1")
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_not_awaited()


@pytest.mark.parametrize("data", [{}, {"token": ""}, {"token": "   "}, {"token": 5}, None, "x"])
async def test_handle_join_rejects_missing_token(data: object) -> None:
    """A join with no usable token errors back to the caller and never enters a room."""
    sio = _fake_sio()

    ack = await handle_join(sio, "sid1", data)

    assert ack["ok"] is False
    assert "error" in ack
    sio.enter_room.assert_not_awaited()
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


# --- DB-backed join tests -------------------------------------------------------


async def test_handle_join_player_enters_room_and_pushes_board_state(
    seeded: SeededBoard,
) -> None:
    """A valid player token joins the resolved room and receives the FULL BoardState."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["roomId"] == str(seeded.room_id)
    assert ack["participantId"] == str(seeded.player_participant_id)
    assert ack["role"] == ParticipantRole.player.value
    assert ack["characterId"] == str(seeded.player_character_id)

    # Entered the room derived from the link (never client-supplied).
    sio.enter_room.assert_awaited_once_with("sid1", room_name(str(seeded.room_id)))

    # The full snapshot was pushed to just this client.
    sio.emit.assert_awaited_once()
    args, kwargs = sio.emit.await_args
    assert args[0] == "boardState"
    assert kwargs == {"to": "sid1"}
    payload = args[1]
    assert payload["room_id"] == str(seeded.room_id)
    assert len(payload["tokens"]) == 1
    assert payload["tokens"][0]["x"] == 3
    assert payload["tokens"][0]["y"] == 4
    assert len(payload["characters"]) == 1
    assert payload["characters"][0]["name"] == "Aria"


async def test_handle_join_host_token_has_no_character(seeded: SeededBoard) -> None:
    """A host token joins the same room with role=host and characterId None."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.host_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["role"] == ParticipantRole.host.value
    assert ack["characterId"] is None
    sio.enter_room.assert_awaited_once_with("sid1", room_name(str(seeded.room_id)))


async def test_handle_join_trims_token(seeded: SeededBoard) -> None:
    """Surrounding whitespace on the token is trimmed before resolution."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": f"  {seeded.player_token}  "}, session_factory=seeded.factory
    )

    assert ack["ok"] is True


async def test_handle_join_unknown_token_is_rejected(seeded: SeededBoard) -> None:
    """An unknown token gets the uniform failure and never enters a room."""
    sio = _fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": "not-a-real-token"}, session_factory=seeded.factory
    )

    assert ack["ok"] is False
    assert ack["error"] == "Invalid or expired invite link."
    sio.enter_room.assert_not_awaited()
    args, _ = sio.emit.await_args
    assert args[0] == "error"


async def test_handle_join_revoked_token_is_rejected(seeded: SeededBoard) -> None:
    """A revoked link cannot join and gets the same uniform failure (no oracle)."""
    async with seeded.factory() as session:
        link = (
            await session.execute(
                select(InviteLink).where(InviteLink.token_hash == hash_token(seeded.player_token))
            )
        ).scalar_one()
        link.revoked_at = dt.datetime.now(dt.UTC)
        await session.commit()

    sio = _fake_sio()
    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is False
    assert ack["error"] == "Invalid or expired invite link."
    sio.enter_room.assert_not_awaited()


async def test_handle_join_stashes_identity_in_session(seeded: SeededBoard) -> None:
    """A successful join saves the resolved identity for later action attribution."""
    sio = _fake_sio()

    await handle_join(sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory)

    sio.save_session.assert_awaited_once()
    args, _ = sio.save_session.await_args
    assert args[0] == "sid1"
    identity = args[1]
    assert isinstance(identity, JoinedIdentity)
    assert identity.room_id == seeded.room_id
    assert identity.role == ParticipantRole.player
    assert identity.participant_id == seeded.player_participant_id
    assert identity.character_id == seeded.player_character_id


# --- action broadcast -----------------------------------------------------------


def _joined(sio: MagicMock, identity: JoinedIdentity) -> None:
    """Bind an authenticated identity to the fake connection (as join would)."""
    sio.get_session = AsyncMock(return_value=identity)


async def _seeded_token_id(seeded: SeededBoard) -> uuid.UUID:
    async with seeded.factory() as session:
        token = (await session.execute(select(Token))).scalar_one()
        return token.id


def _move_intent(token_id: uuid.UUID, x: int, y: int) -> dict[str, object]:
    return {"version": 1, "payload": {"type": "move", "token_id": str(token_id), "x": x, "y": y}}


async def test_handle_action_rejects_when_not_joined() -> None:
    """An action on a connection that never joined is acked-error and not broadcast."""
    sio = _fake_sio()  # default get_session -> {} (no identity)

    ack = await handle_action(
        sio, "sid1", _move_intent(uuid.uuid4(), 1, 1), sequencer=RoomSequencer()
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
    sio = _fake_sio()
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    token_id = await _seeded_token_id(seeded)
    bad = {"version": 999, "payload": {"type": "move", "token_id": str(token_id), "x": 1, "y": 1}}

    ack = await handle_action(
        sio, "sid1", bad, sequencer=RoomSequencer(), session_factory=seeded.factory
    )

    assert ack["ok"] is False
    args, kwargs = sio.emit.await_args
    assert args[0] == "error"
    assert kwargs == {"to": "sid1"}


async def test_handle_action_host_move_broadcasts_and_persists(seeded: SeededBoard) -> None:
    """A host move broadcasts the stamped Action to the room AND moves the token row."""
    sio = _fake_sio()
    actor = uuid.uuid4()
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=actor,
            character_id=None,
        ),
    )
    token_id = await _seeded_token_id(seeded)

    ack = await handle_action(
        sio,
        "sid1",
        _move_intent(token_id, 7, 8),
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
    assert action["payload"] == {"type": "move", "token_id": str(token_id), "x": 7, "y": 8}

    # Durable row reflects the move (reconnect-safe).
    async with seeded.factory() as session:
        token = await session.get(Token, token_id)
        assert token is not None
        assert (token.x, token.y) == (7, 8)


async def test_handle_action_player_damage_persists_clamped(seeded: SeededBoard) -> None:
    """A player damaging their own token reduces HP (clamped at 0) and broadcasts."""
    sio = _fake_sio()
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=seeded.player_character_id,
        ),
    )
    token_id = await _seeded_token_id(seeded)
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


async def test_handle_action_player_cannot_move_foreign_token(seeded: SeededBoard) -> None:
    """A player whose character does not own the token is rejected, never broadcast."""
    sio = _fake_sio()
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=seeded.player_participant_id,
            character_id=uuid.uuid4(),  # not the token's character
        ),
    )
    token_id = await _seeded_token_id(seeded)

    ack = await handle_action(
        sio,
        "sid1",
        _move_intent(token_id, 1, 1),
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
    sio = _fake_sio()
    actor = seeded.player_participant_id
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            participant_id=actor,
            character_id=seeded.player_character_id,
        ),
    )
    token_id = await _seeded_token_id(seeded)
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


async def test_handle_action_seq_is_monotonic_per_room(seeded: SeededBoard) -> None:
    """A shared sequencer hands out increasing seq across actions in the same room."""
    sio = _fake_sio()
    _joined(
        sio,
        JoinedIdentity(
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            participant_id=uuid.uuid4(),
            character_id=None,
        ),
    )
    token_id = await _seeded_token_id(seeded)
    sequencer = RoomSequencer()

    ack1 = await handle_action(
        sio,
        "sid1",
        _move_intent(token_id, 1, 1),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )
    ack2 = await handle_action(
        sio,
        "sid1",
        _move_intent(token_id, 2, 2),
        sequencer=sequencer,
        session_factory=seeded.factory,
    )

    assert ack1["seq"] == 0
    assert ack2["seq"] == 1


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
    token_id = await _seeded_token_id(seeded)

    # 1. Player joins initially and sees the token at its starting cell.
    player_sio = _fake_sio()
    first_ack = await handle_join(
        player_sio, "p-sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )
    assert first_ack["ok"] is True
    args, _ = player_sio.emit.await_args
    assert args[0] == "boardState"
    assert (args[1]["tokens"][0]["x"], args[1]["tokens"][0]["y"]) == (3, 4)
    assert args[1]["characters"][0]["current_hp"] == 20

    # 2. Host moves the token AND damages the character mid-encounter
    #    (durable apply + broadcast on each).
    host_sio = _fake_sio()
    _joined(
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
        _move_intent(token_id, 7, 8),
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
    reconnect_sio = _fake_sio()
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
    assert (board["tokens"][0]["x"], board["tokens"][0]["y"]) == (7, 8)
    assert board["characters"][0]["current_hp"] == 15  # 20 - 5

    # Identity is re-bound on reconnect so the player can keep acting after reload.
    reconnect_sio.save_session.assert_awaited_once()
    identity = reconnect_sio.save_session.await_args.args[1]
    assert isinstance(identity, JoinedIdentity)
    assert identity.participant_id == seeded.player_participant_id


def test_room_sequencer_is_monotonic_and_per_room() -> None:
    sequencer = RoomSequencer()
    assert sequencer.next_seq("a") == 0
    assert sequencer.next_seq("a") == 1
    assert sequencer.next_seq("b") == 0  # independent per room
    assert sequencer.next_seq("a") == 2


# --- registration + mounting ----------------------------------------------------


def test_register_handlers_binds_events() -> None:
    sio = create_sio_server()
    handlers = sio.handlers["/"]
    assert {"connect", "disconnect", "join", "action"} <= set(handlers)


def test_create_sio_server_returns_async_server() -> None:
    sio = create_sio_server()
    assert isinstance(sio, socketio.AsyncServer)


def test_register_handlers_is_callable_on_plain_mock() -> None:
    sio = MagicMock()
    register_handlers(sio)
    registered = {call.args[0] for call in sio.on.call_args_list}
    assert {"connect", "disconnect", "join", "action"} == registered


async def test_combined_asgi_app_serves_fastapi_health() -> None:
    """The wrapped ASGI app forwards non-socket.io requests to FastAPI."""
    app = create_asgi_app(create_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_combined_asgi_app_serves_socketio_handshake() -> None:
    """The wrapped ASGI app answers the Engine.IO handshake under /socket.io/."""
    app = create_asgi_app(create_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/socket.io/?EIO=4&transport=polling")

    assert response.status_code == 200
    assert response.text.startswith("0")
    assert "sid" in response.text
