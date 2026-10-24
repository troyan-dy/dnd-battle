"""DB-backed tests of the token-authenticated realtime ``join``.

A session_factory bound to an in-memory sqlite schema is injected so the
token-authenticated join + FULL BoardState push is exercised end to end.
"""

from __future__ import annotations

import datetime as dt

from app.models import (
    InviteLink,
    ParticipantRole,
)
from app.realtime.connection import JoinedIdentity
from app.realtime.join import handle_join
from app.realtime.rooms import host_room_name, player_room_name, room_name
from app.security.tokens import hash_token
from sqlalchemy import select

from tests.realtime.support import (
    SeededBoard,
    fake_sio,
)

# --- DB-backed join tests -------------------------------------------------------


async def test_handle_join_player_enters_room_and_pushes_board_state(
    seeded: SeededBoard,
) -> None:
    """A valid player token joins the resolved room and receives the FULL BoardState."""
    sio = fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["roomId"] == str(seeded.room_id)
    assert ack["participantId"] == str(seeded.player_participant_id)
    assert ack["role"] == ParticipantRole.player.value
    assert ack["characterId"] == str(seeded.player_character_id)

    # Entered the room derived from the link (never client-supplied), plus the
    # role-specific sub-room used for fog-of-war broadcasts.
    assert sio.enter_room.await_count == 2
    sio.enter_room.assert_any_await("sid1", room_name(str(seeded.room_id)))
    sio.enter_room.assert_any_await("sid1", player_room_name(str(seeded.room_id)))

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
    sio = fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": seeded.host_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is True
    assert ack["role"] == ParticipantRole.host.value
    assert ack["characterId"] is None
    assert sio.enter_room.await_count == 2
    sio.enter_room.assert_any_await("sid1", room_name(str(seeded.room_id)))
    sio.enter_room.assert_any_await("sid1", host_room_name(str(seeded.room_id)))


async def test_handle_join_trims_token(seeded: SeededBoard) -> None:
    """Surrounding whitespace on the token is trimmed before resolution."""
    sio = fake_sio()

    ack = await handle_join(
        sio, "sid1", {"token": f"  {seeded.player_token}  "}, session_factory=seeded.factory
    )

    assert ack["ok"] is True


async def test_handle_join_unknown_token_is_rejected(seeded: SeededBoard) -> None:
    """An unknown token gets the uniform failure and never enters a room."""
    sio = fake_sio()

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

    sio = fake_sio()
    ack = await handle_join(
        sio, "sid1", {"token": seeded.player_token}, session_factory=seeded.factory
    )

    assert ack["ok"] is False
    assert ack["error"] == "Invalid or expired invite link."
    sio.enter_room.assert_not_awaited()


async def test_handle_join_stashes_identity_in_session(seeded: SeededBoard) -> None:
    """A successful join saves the resolved identity for later action attribution."""
    sio = fake_sio()

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
