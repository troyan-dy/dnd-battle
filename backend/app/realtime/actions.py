"""The ``action`` event of the realtime board transport.

The ``action`` handler parses the client's :class:`ActionIntent`, then hands it to
:class:`app.services.dispatch.ActionDispatcher`, which validates it against state +
permissions, applies the durable effect and stamps a server :class:`Action` (id +
monotonic per-room ``seq``). This module only emits the outcome: the Action is
broadcast to everyone in ``room:{roomId}`` (hosts only when it touches a hidden
token). A malformed or unauthorised intent is rejected to the caller and NEVER
broadcast.
"""

from __future__ import annotations

import random
from typing import Any

from pydantic import ValidationError

from app.db.session import async_session_factory
from app.realtime.connection import JoinedIdentity, SessionFactory, load_identity, reject
from app.realtime.rooms import host_room_name, player_room_name, room_name
from app.schemas.action import ActionIntent
from app.schemas.payloads import SetVisibilityPayload
from app.services.dispatch import ActionDispatcher, CommittedAction, RoleBoards
from app.services.intents import IntentValidationError
from app.services.sequence import SequenceCounter

# Rejection shown when an `action` arrives on a connection that never joined a room.
_NOT_JOINED_ERROR = "Join a room before sending actions."
# Rejection for an intent that fails to parse (bad protocol version / bounds / type).
_MALFORMED_ACTION_ERROR = "Malformed or unsupported action."

# Process RNG used for server-authoritative dice rolls (CLAUDE.md rule 1). Tests
# inject a seeded Random for deterministic results.
_DEFAULT_RNG = random.Random()


async def handle_action(  # noqa: WPS211 - documented handler seam, see docstring
    sio: Any,
    sid: str,
    message: Any,
    *,
    sequencer: SequenceCounter,
    rng: random.Random = _DEFAULT_RNG,
    session_factory: SessionFactory = async_session_factory,
) -> dict[str, Any]:
    """Validate a client's action intent, apply it, and broadcast the Action.

    The actor's identity (room / role / character) comes from the join-time
    session, never the client payload. The pipeline is: parse the
    :class:`ActionIntent` (rejecting bad version / bounds / unknown type) ->
    validate (permissions + state) -> apply (durable effect) -> stamp a server
    :class:`Action` with a per-room monotonic ``seq`` -> broadcast ``action`` to
    everyone in the room. Any parse or validation failure is acked back to the
    caller and is NEVER broadcast.

    Besides the Socket.IO arguments (``sio``, ``sid`` and the event payload) the
    handler takes its collaborators — the per-process ``sequencer``, the dice
    ``rng`` and the ``session_factory`` — as keyword arguments so tests inject them.
    """
    identity = await load_identity(sio, sid)
    if identity is None:
        return await reject(sio, sid, _NOT_JOINED_ERROR)

    try:
        intent = ActionIntent.model_validate(message)
    except ValidationError:
        return await reject(sio, sid, _MALFORMED_ACTION_ERROR)

    async with session_factory() as session:
        dispatcher = ActionDispatcher(session, sequencer=sequencer, rng=rng)
        try:
            return await _carry_out(sio, dispatcher, identity=identity, intent=intent)
        except IntentValidationError as exc:
            return await reject(sio, sid, exc.reason)


async def _carry_out(
    sio: Any,
    dispatcher: ActionDispatcher,
    *,
    identity: JoinedIdentity,
    intent: ActionIntent,
) -> dict[str, Any]:
    """Validate + apply ``intent`` through ``dispatcher``, then emit the outcome."""
    payload = await dispatcher.validate(
        intent,
        room_id=identity.room_id,
        role=identity.role,
        character_id=identity.character_id,
    )
    # Fog of war: a visibility change is NOT rebroadcast as an Action (that would
    # leak board info) — each side is RESYNCED with a role-filtered BoardState.
    if isinstance(payload, SetVisibilityPayload):
        boards = await dispatcher.resync_visibility(payload, room_id=identity.room_id)
        return await _push_role_boards(sio, room_key=str(identity.room_id), boards=boards)
    committed = await dispatcher.commit(
        payload,
        room_id=identity.room_id,
        actor_participant_id=identity.participant_id,
    )
    return await _broadcast(sio, room_key=str(identity.room_id), committed=committed)


async def _push_role_boards(sio: Any, *, room_key: str, boards: RoleBoards) -> dict[str, Any]:
    """Resync hosts with the full board and players with the fog-filtered one."""
    await sio.emit(
        "boardState",
        boards.host.model_dump(mode="json"),
        room=host_room_name(room_key),
    )
    await sio.emit(
        "boardState",
        boards.player.model_dump(mode="json"),
        room=player_room_name(room_key),
    )
    return {"ok": True}


async def _broadcast(
    sio: Any,
    *,
    room_key: str,
    committed: CommittedAction,
) -> dict[str, Any]:
    """Broadcast a committed Action and return the caller's success ack.

    Goes to EVERYONE in the room (sender included, which reconciles its optimistic
    move), UNLESS the action touches a hidden token — then only to hosts.
    """
    target_room = host_room_name(room_key) if committed.hosts_only else room_name(room_key)
    action = committed.action
    await sio.emit("action", action.model_dump(mode="json"), room=target_room)
    return {"ok": True, "actionId": str(action.id), "seq": action.seq}
