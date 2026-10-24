"""Fixtures for the realtime transport tests."""

from __future__ import annotations

import pytest_asyncio

from tests.realtime.support import SeededBoard, seed_board
from tests.support import SessionMaker


@pytest_asyncio.fixture
async def seeded(factory: SessionMaker) -> SeededBoard:
    """A room with a host link, a player (character + token), and a player link."""
    return await seed_board(factory)
