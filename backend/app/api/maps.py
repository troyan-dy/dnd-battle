"""Room map API router — upload and stream a room's encounter map image."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app import config
from app.api.dependencies import SessionDep, not_found, require_room, rooms_router
from app.models.room import Room
from app.schemas.room import MapResponse
from app.storage.maps import map_image_path, save_map_image

router = rooms_router()

_MAP_NOT_FOUND = "Map not found."


def build_map_url(room_id: uuid.UUID) -> str:
    """Return the path that streams a room's stored map image."""
    return f"/rooms/{room_id}/map"


@router.post(
    "/{room_id}/map",
    response_model=MapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_map(
    room_id: uuid.UUID,
    # The multipart form field stays named `file` (the public upload contract).
    upload: Annotated[UploadFile, File(alias="file")],
    session: SessionDep,
) -> MapResponse:
    """Host action: upload (or replace) the room's encounter map image.

    No auth gate yet — this follows the same established host-action pattern as
    ``add_player``/``revoke`` (the link is the credential); server-enforced
    permissions are the explicit Phase 7 task. Validation guardrails:

    * the content type must be in the image allowlist (otherwise 415);
    * the body is read with a hard size cap (otherwise 413);
    * the file is stored under a *server-generated* name, so the client filename
      never influences the path (no traversal).

    Re-uploading overwrites the room's map pointer; the previous file is left on
    disk (cleanup is deferred — we never delete user content implicitly).
    """
    room = await require_room(session, room_id)
    content_type = _allowed_content_type(upload)
    image = await _read_capped(upload)

    room.map_image_path = save_map_image(image, content_type)
    room.map_content_type = content_type
    await session.commit()

    return MapResponse(
        room_id=room.id,
        content_type=content_type,
        url=build_map_url(room.id),
    )


@router.get("/{room_id}/map")
async def get_map(
    room_id: uuid.UUID,
    session: SessionDep,
) -> FileResponse:
    """Serve a room's stored map image (reconnect-safe: a plain idempotent read).

    Returns 404 if the room has no map, or its stored file is missing on disk.
    """
    room = await session.get(Room, room_id)
    if room is None or room.map_image_path is None:
        raise not_found(_MAP_NOT_FOUND)

    path = map_image_path(room.map_image_path)
    if not path.is_file():
        raise not_found(_MAP_NOT_FOUND)

    return FileResponse(path, media_type=room.map_content_type or "application/octet-stream")


def _allowed_content_type(upload: UploadFile) -> str:
    """The upload's content type if it is an allowlisted image type (else 415)."""
    content_type = upload.content_type or ""
    if content_type not in config.MAP_CONTENT_TYPE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported map image type. Allowed: PNG, JPEG, WEBP, GIF.",
        )
    return content_type


async def _read_capped(upload: UploadFile) -> bytes:
    """Read a non-empty upload of at most the configured size (else 422 / 413)."""
    # Read at most the cap + 1 byte so an oversized upload never buffers unbounded.
    image = await upload.read(config.MAX_MAP_UPLOAD_BYTES + 1)
    if not image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Empty map image upload.",
        )
    if len(image) > config.MAX_MAP_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Map image exceeds the maximum allowed size.",
        )
    return image
