"""Pydantic request/response contracts for the room API.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
Invite-link plaintext appears in a response model exactly once — when the room
is created — and is never persisted (only its SHA-256 hash is, server-side).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ParticipantRole, RoomStatus
from app.rules.damage import DamageType, Defense

# D&D 2024 ability scores range 1..30 (PHB caps player scores at 20, but monsters
# and magic items can push to 30). 10 is the unmodified human average.
ABILITY_SCORE_MIN = 1
ABILITY_SCORE_MAX = 30
ABILITY_SCORE_DEFAULT = 10

# Armor Class bounds mirror the rules engine (app.rules.attack MIN/MAX_ARMOR_CLASS).
# 10 is the 2024 unarmored baseline an attack must meet or beat to hit.
ARMOR_CLASS_MIN = 1
ARMOR_CLASS_MAX = 50
ARMOR_CLASS_DEFAULT = 10

# Board grid coordinate bounds. The server has no map-grid dimensions yet (the
# grid is configured client-side), so we only enforce non-negativity plus a sane
# upper cap to reject abusive values. Token footprint is measured in grid cells:
# 1 = Tiny/Small/Medium, 2 = Large, 3 = Huge, 4 = Gargantuan (D&D 2024 sizes).
GRID_COORD_MIN = 0
GRID_COORD_MAX = 9999
TOKEN_SIZE_MIN = 1
TOKEN_SIZE_MAX = 8
TOKEN_SIZE_DEFAULT = 1

# Initiative roll bounds. A d20 initiative + modifiers realistically stays well
# within these; we cap to reject abusive values while allowing big negatives.
INITIATIVE_MIN = -50
INITIATIVE_MAX = 100
# A host may seat at most this many combatants in one turn order.
INITIATIVE_MAX_ENTRIES = 100


class AbilityScores(BaseModel):
    """The six D&D 2024 ability scores. Each defaults to the average (10)."""

    strength: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    constitution: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    intelligence: int = Field(
        default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX
    )
    wisdom: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(default=ABILITY_SCORE_DEFAULT, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)


class CreateRoomRequest(BaseModel):
    """Host's request to open a new encounter session."""

    name: str = Field(min_length=1, max_length=120, description="Encounter / room name.")
    host_display_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional friendly name shown for the DM.",
    )


class RoomSummary(BaseModel):
    """Public view of a freshly created room."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: RoomStatus


class InviteLinkResponse(BaseModel):
    """A shareable invite link. ``token`` is a secret returned only at creation."""

    token: str = Field(description="Plaintext invite token — shown once, never stored.")
    url: str = Field(description="Full shareable URL: {APP_BASE_URL}/join/{token}.")


class CreateRoomResponse(BaseModel):
    """Result of creating a room: the room, the host participant, and host link."""

    room: RoomSummary
    host_participant_id: uuid.UUID
    host_role: ParticipantRole
    host_link: InviteLinkResponse


class AddPlayerRequest(BaseModel):
    """Host's request to add a player participant + their character slot to a room."""

    character_name: str = Field(
        min_length=1,
        max_length=120,
        description="Name of the character slot the player will control.",
    )
    max_hp: int = Field(gt=0, le=1000, description="The character's maximum hit points.")
    ability_scores: AbilityScores = Field(
        default_factory=AbilityScores,
        description="The six D&D 2024 ability scores; each defaults to 10 if omitted.",
    )
    armor_class: int = Field(
        default=ARMOR_CLASS_DEFAULT,
        ge=ARMOR_CLASS_MIN,
        le=ARMOR_CLASS_MAX,
        description="Armor Class an attack roll must meet to hit (defaults to 10).",
    )
    resistances: dict[str, str] = Field(
        default_factory=dict,
        description="Damage-type defenses, e.g. {'fire': 'resistance'}; absent type = normal.",
    )
    portrait_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional http(s) URL of a portrait image for the character.",
    )
    display_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional friendly name shown for the player.",
    )

    @field_validator("resistances")
    @classmethod
    def _validate_resistances(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject unknown damage types or defense values; drop plain 'normal' entries."""
        cleaned: dict[str, str] = {}
        for raw_type, raw_defense in value.items():
            try:
                damage_type = DamageType(raw_type)
                defense = Defense(raw_defense)
            except ValueError as exc:
                raise ValueError(f"invalid resistance entry {raw_type!r}: {raw_defense!r}") from exc
            if defense is not Defense.NORMAL:
                cleaned[damage_type.value] = defense.value
        return cleaned

    @field_validator("portrait_url")
    @classmethod
    def _validate_portrait_url(cls, value: str | None) -> str | None:
        """Normalize empty/blank to None; require an http(s) scheme when present."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
            raise ValueError("portrait_url must be an http:// or https:// URL.")
        return trimmed


class AddPlayerResponse(BaseModel):
    """Result of adding a player: the participant, their character, and invite link.

    The invite link is bound to (room, participant, character): opening it later
    resolves the player to exactly this character slot.
    """

    participant_id: uuid.UUID
    character_id: uuid.UUID
    role: ParticipantRole
    invite_link: InviteLinkResponse


class RevokeLinksResponse(BaseModel):
    """Result of revoking a participant's invite link(s).

    ``revoked`` is the number of *previously active* links that this call
    disabled. The endpoint is idempotent: a second call revokes ``0`` more,
    because already-revoked (or expired) links are left untouched.
    """

    revoked: int = Field(ge=0, description="How many active links this call revoked.")


class MapResponse(BaseModel):
    """Result of uploading (or describing) a room's current map image.

    ``url`` is the server path that streams the stored image back
    (``GET /rooms/{room_id}/map``); the bytes themselves are never inlined here.
    """

    room_id: uuid.UUID
    content_type: str = Field(description="Validated image MIME type of the stored map.")
    url: str = Field(description="Path that serves the map image: /rooms/{room_id}/map.")


class PlaceTokenRequest(BaseModel):
    """Host's request to place a token for a character on the board grid.

    Binds the new token to ``character_id`` (which must belong to the room). A
    character may have at most one token, so placing a second one is a conflict.
    """

    character_id: uuid.UUID = Field(description="Character this token represents.")
    x: int = Field(
        default=0, ge=GRID_COORD_MIN, le=GRID_COORD_MAX, description="Grid column (0-based)."
    )
    y: int = Field(
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

    x: int | None = Field(default=None, ge=GRID_COORD_MIN, le=GRID_COORD_MAX)
    y: int | None = Field(default=None, ge=GRID_COORD_MIN, le=GRID_COORD_MAX)
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
    x: int
    y: int
    size: int
    hidden: bool = False


class CharacterResponse(BaseModel):
    """Read view of a character's stat block.

    Returned by ``GET /rooms/{room_id}/characters/{character_id}`` so a player view
    can render the player's own character panel after the invite resolves to a
    ``character_id``. A plain idempotent read (reconnect-safe); no secrets.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    name: str
    max_hp: int
    current_hp: int
    armor_class: int
    portrait_url: str | None
    ability_scores: AbilityScores
    resistances: dict[str, str]
    conditions: list[str]


class ResolveInviteResponse(BaseModel):
    """Result of resolving an invite token -> who/where the link binds the visitor.

    Returned by ``GET /invites/{token}`` for a valid, active link. ``character_id``
    is ``None`` for a host (the DM controls no single character slot).
    """

    room_id: uuid.UUID
    participant_id: uuid.UUID
    role: ParticipantRole
    character_id: uuid.UUID | None


class InitiativeEntryInput(BaseModel):
    """One combatant the host seats in the turn order when setting initiative.

    Either bind it to an existing ``character_id`` (which must belong to the room)
    or leave it ``None`` for an NPC/monster; ``name`` is the display label shown in
    the tracker. ``initiative`` is the rolled value (higher acts first).
    """

    character_id: uuid.UUID | None = Field(
        default=None, description="Character this combatant represents, or None for an NPC."
    )
    name: str = Field(min_length=1, max_length=120, description="Display label in the tracker.")
    initiative: int = Field(
        ge=INITIATIVE_MIN, le=INITIATIVE_MAX, description="Rolled initiative (higher acts first)."
    )


class SetInitiativeRequest(BaseModel):
    """Host's request to (re)build a room's initiative order.

    Replaces any existing order. Entries are sorted by ``initiative`` descending
    (ties broken stably by the order given); the active turn resets to the first
    combatant and the round counter resets to 1.
    """

    entries: list[InitiativeEntryInput] = Field(
        default_factory=list,
        max_length=INITIATIVE_MAX_ENTRIES,
        description="Combatants to seat in the turn order (empty clears it).",
    )


class InitiativeEntryResponse(BaseModel):
    """Read view of one combatant's seat in the turn order."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    character_id: uuid.UUID | None
    name: str
    initiative: int
    order_index: int


class InitiativeState(BaseModel):
    """The full turn-order snapshot: the ordered combatants + whose turn it is.

    ``active_index`` is the 0-based seat whose turn it currently is (``None`` when
    no order is set = combat not started); ``round`` counts rounds. Part of the
    reconnect-safe :class:`BoardState`, so a client that reloads its link rebuilds
    the tracker exactly (CLAUDE.md rule 2).
    """

    active_index: int | None
    round: int
    entries: list[InitiativeEntryResponse]


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
