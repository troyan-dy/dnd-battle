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
from app.schemas.room import BoardState, CharacterResponse, TokenResponse
from app.services.initiative import build_initiative_state


async def build_board_state(session: AsyncSession, room_id: uuid.UUID) -> BoardState:
    """Assemble the full BoardState for ``room_id`` from persisted rows.

    Joins the placed tokens, their character stat blocks, and the initiative
    turn-order snapshot — everything a (re)joining client needs to render the board.
    """
    tokens = (await session.execute(select(Token).where(Token.room_id == room_id))).scalars().all()
    characters = (
        (await session.execute(select(Character).where(Character.room_id == room_id)))
        .scalars()
        .all()
    )
    initiative = await build_initiative_state(session, room_id)
    return BoardState(
        room_id=room_id,
        tokens=[TokenResponse.model_validate(t) for t in tokens],
        characters=[CharacterResponse.model_validate(c) for c in characters],
        initiative=initiative,
    )
