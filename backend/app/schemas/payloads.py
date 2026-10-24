"""Per-action payloads of the versioned Action protocol (board actions).

Each payload is one member of the ``type``-discriminated unions assembled in
:mod:`app.schemas.action`; the attack payloads live in :mod:`app.schemas.attack`.
This module is pure schema: the Pydantic *source of truth* the TS client mirrors.
"""

from __future__ import annotations

import enum
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.token import GRID_COORD_MAX, GRID_COORD_MIN

# Damage / healing magnitudes. Capped at the max-HP ceiling (character.AddPlayerRequest
# limits max_hp to 1000) so a single action can never apply an absurd amount.
DAMAGE_AMOUNT_MIN = 1
DAMAGE_AMOUNT_MAX = 1000
HEAL_AMOUNT_MIN = 1
HEAL_AMOUNT_MAX = 1000

# Cosmetic bounds for a board mark/ping.
MARK_LABEL_MAX_LENGTH = 60
MARK_COLOR_MAX_LENGTH = 32

# NOTE: `x` / `y` (WPS111 short names) are the public grid-coordinate field names of
# the Action protocol (mirrored by the TS client), so they keep their short names.


class ActionType(enum.StrEnum):
    """Discriminator values for the per-action payloads."""

    MOVE = "move"
    MARK = "mark"
    DAMAGE = "damage"
    HEAL = "heal"
    ATTACK = "attack"
    END_TURN = "endTurn"
    SET_VISIBILITY = "setVisibility"


class MovePayload(BaseModel):
    """Move a token to a grid cell. Bounds mirror the placement contract."""

    type: Literal[ActionType.MOVE] = ActionType.MOVE
    token_id: uuid.UUID = Field(description="Token being moved.")
    x: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Target grid column.")  # noqa: WPS111
    y: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Target grid row.")  # noqa: WPS111


class MarkPayload(BaseModel):
    """A transient mark / ping placed on the board for everyone to see."""

    type: Literal[ActionType.MARK] = ActionType.MARK
    x: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Mark grid column.")  # noqa: WPS111
    y: int = Field(ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Mark grid row.")  # noqa: WPS111
    color: str | None = Field(
        default=None, max_length=MARK_COLOR_MAX_LENGTH, description="Optional display color."
    )
    label: str | None = Field(
        default=None, max_length=MARK_LABEL_MAX_LENGTH, description="Optional short label."
    )


class DamagePayload(BaseModel):
    """Apply damage to a token, reducing its character's HP (clamped at 0).

    Damage and healing are deliberately SEPARATE action types (not one signed
    amount): the discriminated union is additive, so they parse independently and
    stay semantically distinct for the upcoming combat log.
    """

    type: Literal[ActionType.DAMAGE] = ActionType.DAMAGE
    token_id: uuid.UUID = Field(description="Token taking damage.")
    amount: int = Field(
        ge=DAMAGE_AMOUNT_MIN, le=DAMAGE_AMOUNT_MAX, description="Hit points of damage to apply."
    )


class HealPayload(BaseModel):
    """Heal a token, restoring its character's HP (clamped at its max HP).

    The mirror of :class:`DamagePayload`: a positive ``amount`` of hit points
    added back, never exceeding the character's maximum.
    """

    type: Literal[ActionType.HEAL] = ActionType.HEAL
    token_id: uuid.UUID = Field(description="Token being healed.")
    amount: int = Field(
        ge=HEAL_AMOUNT_MIN, le=HEAL_AMOUNT_MAX, description="Hit points of healing to apply."
    )


class SetVisibilityPayload(BaseModel):
    """Host → server: hide or reveal a token on the board (fog of war).

    HOST-ONLY (enforced in :func:`app.services.intents.validate_intent`). This is
    an INTENT-only payload: the server does not rebroadcast it as an Action — a
    visibility change leaks board info, so instead the server applies the durable
    ``Token.hidden`` flip and pushes a fresh, role-FILTERED :class:`BoardState` to
    each side (players never receive a hidden token). It therefore appears in the
    intent union only, not the broadcast union (mirrors the attack-intent split).
    """

    type: Literal[ActionType.SET_VISIBILITY] = ActionType.SET_VISIBILITY
    token_id: uuid.UUID = Field(description="Token to hide or reveal.")
    hidden: bool = Field(description="True hides the token from players; False reveals it.")


class EndTurnPayload(BaseModel):
    """Advance the initiative order to the next combatant. Carries no data."""

    type: Literal[ActionType.END_TURN] = ActionType.END_TURN
