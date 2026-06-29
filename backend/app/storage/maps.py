"""Filesystem persistence for room map images.

File I/O is isolated here so the transport layer (the API router) stays free of
disk concerns. Map files are written with a *server-generated* name derived from
a validated, allowlisted content type — the client-supplied filename is never
used in the stored path, which removes any path-traversal surface.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app import config


def storage_dir() -> Path:
    """Return the map storage directory, creating it if needed."""
    path = Path(config.MAP_STORAGE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_map_image(data: bytes, content_type: str) -> str:
    """Persist ``data`` and return the server-generated relative filename.

    ``content_type`` must already be an allowlisted key of
    :data:`app.config.MAP_CONTENT_TYPE_EXTENSIONS`; the caller validates it.
    """
    extension = config.MAP_CONTENT_TYPE_EXTENSIONS[content_type]
    filename = f"{uuid.uuid4().hex}{extension}"
    (storage_dir() / filename).write_bytes(data)
    return filename


def map_image_path(filename: str) -> Path:
    """Resolve a stored map filename to its absolute path on disk."""
    return storage_dir() / filename
