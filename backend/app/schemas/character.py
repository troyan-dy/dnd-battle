"""Pydantic contracts for characters: adding a player slot and reading a stat block.

These are the source-of-truth shapes (CLAUDE.md): the TS client mirrors them.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.limits import NAME_MAX_LENGTH, URL_MAX_LENGTH
from app.models.enums import ParticipantRole
from app.rules.damage import DamageType, Defense
from app.schemas.invite import InviteLinkResponse

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


def _parse_resistance(raw_type: str, raw_defense: str) -> tuple[DamageType, Defense]:
    """Parse one ``{damage_type: defense}`` entry, rejecting unknown values."""
    try:
        return DamageType(raw_type), Defense(raw_defense)
    except ValueError as exc:
        raise ValueError(f"invalid resistance entry {raw_type!r}: {raw_defense!r}") from exc


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


class AddPlayerRequest(BaseModel):
    """Host's request to add a player participant + their character slot to a room."""

    character_name: str = Field(
        min_length=1,
        max_length=NAME_MAX_LENGTH,
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
        max_length=URL_MAX_LENGTH,
        description="Optional http(s) URL of a portrait image for the character.",
    )
    display_name: str | None = Field(
        default=None,
        max_length=NAME_MAX_LENGTH,
        description="Optional friendly name shown for the player.",
    )

    @field_validator("resistances")
    @classmethod
    def _validate_resistances(cls, resistances: dict[str, str]) -> dict[str, str]:
        """Reject unknown damage types or defense values; drop plain 'normal' entries."""
        cleaned: dict[str, str] = {}
        for raw_type, raw_defense in resistances.items():
            damage_type, defense = _parse_resistance(raw_type, raw_defense)
            if defense is not Defense.NORMAL:
                cleaned[damage_type.value] = defense.value
        return cleaned

    @field_validator("portrait_url")
    @classmethod
    def _validate_portrait_url(cls, portrait_url: str | None) -> str | None:
        """Normalize empty/blank to None; require an http(s) scheme when present."""
        if portrait_url is None:
            return None
        trimmed = portrait_url.strip()
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
