"""Socket.IO server construction and ASGI mounting.

``create_sio_server`` builds an ``AsyncServer`` (ASGI mode) with the board event
handlers registered and CORS locked to the allowlisted SPA origins.
``create_asgi_app`` wraps it together with the FastAPI HTTP app so a single ASGI
callable serves both the REST API and the ``/socket.io`` realtime endpoint —
exactly what ``uvicorn app.main:app`` runs.
"""

from __future__ import annotations

from typing import Any

import socketio

from app import config
from app.realtime.events import register_handlers

# Path the Engine.IO/Socket.IO handshake + transport requests are served under.
# The client must use the same path (it is the socket.io default).
SOCKETIO_PATH = "socket.io"


def create_sio_server() -> Any:
    """Build a configured ``AsyncServer`` with board handlers registered.

    CORS is restricted to the allowlisted SPA origins (``config.SOCKETIO_CORS_ORIGINS``)
    because the browser opens the realtime connection from a different origin than
    the API in dev and prod.
    """
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=config.SOCKETIO_CORS_ORIGINS,
    )
    register_handlers(sio)
    return sio


def create_asgi_app(fastapi_app: Any, sio: Any | None = None) -> Any:
    """Wrap the FastAPI app and a Socket.IO server into one ASGI application.

    Non-Socket.IO requests (the REST API, ``/health``) are forwarded to
    ``fastapi_app``; requests under ``/socket.io`` are handled by ``sio``. A
    server is created if one is not supplied (handy for tests).
    """
    if sio is None:
        sio = create_sio_server()
    return socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path=SOCKETIO_PATH)
