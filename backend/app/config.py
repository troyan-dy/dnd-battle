"""Runtime configuration sourced from environment variables.

Kept deliberately tiny (stdlib only) so importing models/migrations never
requires a running database or extra settings dependency. The async SQLAlchemy
URL defaults to a local sqlite file so tests and offline tooling work without
Postgres; production/dev set ``DATABASE_URL`` to the asyncpg Postgres URL
(see ``.env.example``).
"""

import os

# Async driver URL. Postgres in real deployments; sqlite+aiosqlite as a
# zero-infra default for unit tests and local schema tooling.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./dnd_battle.db",
)

# Public origin of the player-facing frontend, used to build shareable invite
# links (e.g. ``{APP_BASE_URL}/join/{token}``). No trailing slash. Override per
# environment; the Vite dev server default keeps local end-to-end flows working.
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")

# ---------------------------------------------------------------------------
# Map image storage. Uploaded encounter maps live on the local filesystem under
# this directory (a zero-infra default; swap for object storage when scaling,
# behind the same API contract). Files are written with server-generated names,
# so the directory only ever contains app-controlled paths.
# ---------------------------------------------------------------------------
MAP_STORAGE_DIR: str = os.getenv("MAP_STORAGE_DIR", "./var/map_uploads")

# Hard cap on a single map upload (bytes). Default 10 MiB. The upload handler
# reads at most this many bytes + 1 so an oversized body never buffers unbounded.
MAX_MAP_UPLOAD_BYTES: int = int(os.getenv("MAX_MAP_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# Allowlisted image MIME types for map uploads. Anything else is rejected (415)
# before touching disk; the stored file extension is derived from this mapping,
# never from the client-supplied filename.
MAP_CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _split_origins(raw: str) -> list[str]:
    """Parse a comma-separated origins string into a de-duplicated, ordered list."""
    seen: dict[str, None] = {}
    for part in raw.split(","):
        origin = part.strip().rstrip("/")
        if origin and origin not in seen:
            seen[origin] = None
    return list(seen)


# Origins allowed to open a realtime Socket.IO connection. The SPA runs on a
# different origin from the API in dev (Vite) and prod, so the websocket/polling
# handshake must be explicitly allowlisted by the Socket.IO server. Comma-separated
# env override; defaults cover the configured public frontend origin plus the Vite
# dev server so local end-to-end flows work out of the box.
SOCKETIO_CORS_ORIGINS: list[str] = _split_origins(
    os.getenv("SOCKETIO_CORS_ORIGINS", f"{APP_BASE_URL},http://localhost:5173")
)
