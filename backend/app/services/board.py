"""Build the FULL current BoardState snapshot for a room.

The live board (CLAUDE.md) is hydrated from the durable, server-authoritative
rows: :class:`Token` placements joined with their :class:`Character` stat blocks.
``build_board_state`` reads those rows and returns the complete snapshot a client
needs to render the board on (re)join — a plain idempotent read, so a client that
reloads its link always receives the same authoritative state (reconnect-safe,
CLAUDE.md rule 2).

A persistent in-memory mutable BoardState is intentionally NOT introduced here;
that belongs with the Action-protocol / broadcast tasks. Reading from the rows on
join keeps this task to the "send full state" scope and matches the existing
two-call frontend hydrate (listTokens + listCharacters), now delivered in one push.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.token import Token
from app.schemas.board import BoardState
from app.schemas.character import CharacterResponse
from app.schemas.token import TokenResponse
from app.services.initiative import build_initiative_state


async def build_board_state(
    session: AsyncSession,
    room_id: uuid.UUID,
    *,
    include_hidden: bool = True,
) -> BoardState:
    """Assemble the full BoardState for ``room_id`` from persisted rows.

    Joins the placed tokens, their character stat blocks, and the initiative
    turn-order snapshot — everything a (re)joining client needs to render the board.

    Fog of war (CLAUDE.md rule 3, enforced on the SERVER): when ``include_hidden``
    is ``False`` (a PLAYER view) the host's hidden tokens are stripped, AND any
    character referenced ONLY by a hidden token is stripped too — so a player can
    neither render a hidden token nor read its stat block off the wire. The host
    view (``include_hidden=True``, the default) receives everything, with each
    token's ``hidden`` flag, so the host can render hidden pieces distinctly.
    """
    tokens = await _room_rows(session, Token, room_id)
    characters = await _room_rows(session, Character, room_id)
    initiative = await build_initiative_state(session, room_id)

    if not include_hidden:
        tokens = [token for token in tokens if not token.hidden]
        # Only keep characters a visible token binds to, so a hidden monster's
        # stat block is never delivered to a player.
        visible_character_ids = {token.character_id for token in tokens}
        characters = [
            character for character in characters if character.id in visible_character_ids
        ]

    return BoardState(
        room_id=room_id,
        tokens=[TokenResponse.model_validate(token) for token in tokens],
        characters=[CharacterResponse.model_validate(character) for character in characters],
        initiative=initiative,
    )


async def _room_rows[RowT: (Token, Character)](
    session: AsyncSession,
    model: type[RowT],
    room_id: uuid.UUID,
) -> list[RowT]:
    """Every persisted ``model`` row (tokens or characters) belonging to ``room_id``."""
    in_room = select(model).where(model.room_id == room_id)
    return list(await session.scalars(in_room))
