"""The full BoardState snapshot contract pushed to a client on (re)join.

This is the source-of-truth shape (CLAUDE.md): the TS client mirrors it.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.character import CharacterResponse
from app.schemas.initiative import InitiativeState
from app.schemas.token import TokenResponse


class BoardState(BaseModel):
    """The FULL current board snapshot pushed to a client when it (re)joins a room.

    This is the authoritative state a client renders the board from: every placed
    ``token``, the ``character`` stat blocks they bind to, and the ``initiative``
    turn order. It is a complete, idempotent read (reconnect-safe, CLAUDE.md rule
    2) — reloading a link yields the same snapshot, never a delta.
    """

    room_id: uuid.UUID
    tokens: list[TokenResponse]
    characters: list[CharacterResponse]
    initiative: InitiativeState
