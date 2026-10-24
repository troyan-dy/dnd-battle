"""Pydantic contracts for board tokens: placing, moving / resizing and reading them.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

# Board grid coordinate bounds. The server has no map-grid dimensions yet (the
# grid is configured client-side), so we only enforce non-negativity plus a sane
# upper cap to reject abusive values. Token footprint is measured in grid cells:
# 1 = Tiny/Small/Medium, 2 = Large, 3 = Huge, 4 = Gargantuan (D&D 2024 sizes).
GRID_COORD_MIN = 0
GRID_COORD_MAX = 9999
TOKEN_SIZE_MIN = 1
TOKEN_SIZE_MAX = 8
TOKEN_SIZE_DEFAULT = 1

# NOTE: `x` / `y` (WPS111 short names) are the public grid-coordinate field names of
# the Token contract (CLAUDE.md: ``{ x, y }``) mirrored by the TS client.


class PlaceTokenRequest(BaseModel):
    """Host's request to place a token for a character on the board grid.

    Binds the new token to ``character_id`` (which must belong to the room). A
    character may have at most one token, so placing a second one is a conflict.
    """

    character_id: uuid.UUID = Field(description="Character this token represents.")
    x: int = Field(  # noqa: WPS111
        default=0, ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Grid column (0-based)."
    )
    y: int = Field(  # noqa: WPS111
        default=0, ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Grid row (0-based)."
    )
    size: int = Field(
        default=TOKEN_SIZE_DEFAULT,
        ge=TOKEN_SIZE_MIN,
        le=TOKEN_SIZE_MAX,
        description="Footprint in grid cells (1 = Medium, 2 = Large, ...).",
    )


class UpdateTokenRequest(BaseModel):
    """Host's request to reposition / resize an existing token.

    Every field is optional; omitted fields are left unchanged. At least one must
    be provided (enforced in the endpoint).
    """

    x: int | None = Field(default=None, ge=GRID_COORD_MIN, le=GRID_COORD_MAX)  # noqa: WPS111
    y: int | None = Field(default=None, ge=GRID_COORD_MIN, le=GRID_COORD_MAX)  # noqa: WPS111
    size: int | None = Field(default=None, ge=TOKEN_SIZE_MIN, le=TOKEN_SIZE_MAX)


class TokenResponse(BaseModel):
    """Board-state view of a single token: its binding and grid placement.

    ``hidden`` is the fog-of-war flag the host controls. A player NEVER receives a
    hidden token (the server filters them out of the player BoardState), so any
    token a client holds with ``hidden=True`` was delivered to a host, who renders
    it distinctly (CLAUDE.md rule 3 — enforced on the server).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    character_id: uuid.UUID
    x: int  # noqa: WPS111
    y: int  # noqa: WPS111
    size: int
    hidden: bool = False
