"""Shared building blocks of the HTTP routers: the DB-session dependency + lookups.

Every room-scoped router is mounted under ``/rooms`` with the ``rooms`` tag, takes
a request-scoped :class:`AsyncSession` via :data:`SessionDep`, and answers an
unknown room with the same uniform 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.room import Room

# A request-scoped DB session injected into every endpoint.
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_ROOM_NOT_FOUND = "Room not found."


def rooms_router() -> APIRouter:
    """A router for one slice of the room API (``/rooms/...``, tagged ``rooms``)."""
    return APIRouter(prefix="/rooms", tags=["rooms"])


def not_found(detail: str) -> HTTPException:
    """A 404 carrying ``detail`` (callers ``raise`` it)."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    """A 422 carrying ``detail`` (callers ``raise`` it)."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


async def require_room(session: AsyncSession, room_id: uuid.UUID) -> Room:
    """Load the room ``room_id`` or raise the uniform "Room not found." 404."""
    room = await session.get(Room, room_id)
    if room is None:
        raise not_found(_ROOM_NOT_FOUND)
    return room
