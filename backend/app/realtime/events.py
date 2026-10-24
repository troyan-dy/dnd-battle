"""Socket.IO event registration for the realtime board transport.

This module owns the connection lifecycle and wires every board event to its
handler: ``join`` (:mod:`app.realtime.join` — the authenticated handshake that
enters the room and pushes the FULL BoardState) and ``action``
(:mod:`app.realtime.actions` — validate, apply and broadcast a client intent).

On a successful join the resolved identity is stashed in the per-connection
Socket.IO session (``save_session``) so a later ``action`` event can be attributed
to an authenticated actor without trusting the client. A malformed or
unauthorised intent is rejected to the caller and NEVER broadcast.

Handler bodies are kept as plain, fully-typed module functions and registered via
``sio.on(name, handler)`` (rather than decorators) so they stay unit-testable with
a fake server and so static typing is unaffected by the untyped Socket.IO library.
"""

from __future__ import annotations

import random
from typing import Any, final

from app.realtime.actions import handle_action
from app.realtime.join import handle_join
from app.realtime.sequence import RoomSequencer


async def handle_connect(sio: Any, sid: str, environ: Any, auth: Any = None) -> bool:
    """Accept a new Socket.IO connection.

    Returning ``True`` accepts the connection. Identity is bound on ``join`` (which
    carries the invite token), so the bare connection accepts without an auth check.
    """
    return True


async def handle_disconnect(sio: Any, sid: str) -> None:
    """Handle a client disconnect.

    Socket.IO automatically removes the ``sid`` from every room it had joined, so
    there is nothing to clean up until a live in-memory BoardState exists.
    """


@final
class _BoardEventHandlers:
    """Per-server Socket.IO callbacks forwarding to the testable module functions.

    Each bound method passes the ``sio`` server instance through explicitly. A single
    :class:`RoomSequencer` (and dice RNG) is created per server and shared, so every
    broadcast Action gets a per-room monotonic ``seq`` for this server process.
    """

    def __init__(self, sio: Any) -> None:
        self._sio = sio
        self._sequencer = RoomSequencer()
        self._rng = random.Random()

    async def connect(self, sid: str, environ: Any, auth: Any = None) -> bool:
        return await handle_connect(self._sio, sid, environ, auth)

    async def disconnect(self, sid: str) -> None:
        await handle_disconnect(self._sio, sid)

    async def join(self, sid: str, message: Any) -> dict[str, Any]:
        return await handle_join(self._sio, sid, message)

    async def action(self, sid: str, message: Any) -> dict[str, Any]:
        return await handle_action(
            self._sio,
            sid,
            message,
            sequencer=self._sequencer,
            rng=self._rng,
        )


def register_handlers(sio: Any) -> None:
    """Attach the connection-lifecycle, ``join`` and ``action`` handlers to a server.

    Handlers are bound methods of one per-server :class:`_BoardEventHandlers`, which
    forward to the testable module functions, passing the ``sio`` server instance
    through explicitly.
    """
    handlers = _BoardEventHandlers(sio)
    sio.on("connect", handlers.connect)
    sio.on("disconnect", handlers.disconnect)
    sio.on("join", handlers.join)
    sio.on("action", handlers.action)
