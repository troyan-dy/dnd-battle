"""Fixtures for the action-service tests."""

from __future__ import annotations

import pytest_asyncio

from tests.actions.support import Seeded, seed_actions_board
from tests.support import SessionMaker


@pytest_asyncio.fixture
async def seeded(factory: SessionMaker) -> Seeded:
    """Two player tokens in one room plus a token in a different room."""
    return await seed_actions_board(factory)
