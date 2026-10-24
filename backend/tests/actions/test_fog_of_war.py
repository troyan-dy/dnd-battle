"""Fog-of-war tests for the action services: the hidden flag and filtered boards."""

from __future__ import annotations

from app.models import (
    Token,
)
from app.schemas.payloads import (
    SetVisibilityPayload,
)
from app.services.actions import apply_action
from app.services.board import build_board_state

from tests.actions.support import Seeded


async def _apply_visibility(seeded: Seeded, *, hidden: bool) -> bool:
    """Apply + commit a ``setVisibility`` for token 2; return its reloaded flag."""
    async with seeded.factory() as session:
        await apply_action(
            session,
            room_id=seeded.room_id,
            payload=SetVisibilityPayload(token_id=seeded.token2_id, hidden=hidden),
        )
        await session.commit()
    async with seeded.factory() as session:
        token = await session.get(Token, seeded.token2_id)
        assert token is not None
        return token.hidden


async def test_apply_set_visibility_flips_hidden_flag(seeded: Seeded) -> None:
    """apply_action toggles the durable Token.hidden flag both ways."""
    assert await _apply_visibility(seeded, hidden=True) is True
    assert await _apply_visibility(seeded, hidden=False) is False


async def test_build_board_state_filters_hidden_tokens_for_players(seeded: Seeded) -> None:
    """A player BoardState excludes hidden tokens AND their characters; host sees all."""
    async with seeded.factory() as session:
        token2 = await session.get(Token, seeded.token2_id)
        assert token2 is not None
        token2.hidden = True
        await session.commit()

    async with seeded.factory() as session:
        host_board = await build_board_state(session, seeded.room_id, include_hidden=True)
        player_board = await build_board_state(session, seeded.room_id, include_hidden=False)

    # Host receives every token (with the hidden flag) and every character.
    host_token_ids = {token.id for token in host_board.tokens}
    assert {seeded.token1_id, seeded.token2_id} <= host_token_ids
    hidden_token_ids = {token.id for token in host_board.tokens if token.hidden}
    assert seeded.token2_id in hidden_token_ids
    assert {seeded.p1_character_id, seeded.p2_character_id} <= {
        character.id for character in host_board.characters
    }

    # The player never receives the hidden token nor its character stat block.
    player_token_ids = {token.id for token in player_board.tokens}
    assert seeded.token1_id in player_token_ids
    assert seeded.token2_id not in player_token_ids
    player_character_ids = {character.id for character in player_board.characters}
    assert seeded.p1_character_id in player_character_ids
    assert seeded.p2_character_id not in player_character_ids
