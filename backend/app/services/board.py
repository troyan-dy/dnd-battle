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
    tokens = list(
        (await session.execute(select(Token).where(Token.room_id == room_id))).scalars().all()
    )
    characters = list(
        (await session.execute(select(Character).where(Character.room_id == room_id)))
        .scalars()
        .all()
    )
    initiative = await build_initiative_state(session, room_id)

    if not include_hidden:
        tokens = [t for t in tokens if not t.hidden]
        # Only keep characters a visible token binds to, so a hidden monster's
        # stat block is never delivered to a player.
        visible_character_ids = {t.character_id for t in tokens}
        characters = [c for c in characters if c.id in visible_character_ids]

    return BoardState(
        room_id=room_id,
        tokens=[TokenResponse.model_validate(t) for t in tokens],
        characters=[CharacterResponse.model_validate(c) for c in characters],
        initiative=initiative,
    )
