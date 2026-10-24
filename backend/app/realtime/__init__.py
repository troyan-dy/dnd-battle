"""Realtime transport for the D&D battler board (Socket.IO over ASGI).

The Socket.IO server is mounted alongside the FastAPI HTTP app (see
``app.main``). This package owns the connection lifecycle and the Socket.IO
room model; the authoritative BoardState, versioned Action protocol, server-side
intent validation and broadcasting arrive in later Phase 4 tasks.
"""

# Redundant ``as`` aliases mark these names as explicit re-exports (PEP 484).
from app.realtime.server import create_asgi_app as create_asgi_app
from app.realtime.server import create_sio_server as create_sio_server
