"""Shared test types and helpers (fixtures live in ``conftest.py``)."""

from __future__ import annotations

import random

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# A session factory bound to the per-test in-memory database.
SessionMaker = async_sessionmaker[AsyncSession]

# The ASGI test client plus the session factory of the database it talks to.
ClientFactory = tuple[httpx.AsyncClient, SessionMaker]


class ScriptedRandom(random.Random):
    """A Random whose ``randint`` returns a fixed script of results, in order.

    Makes server-authoritative dice deterministic: the script lists each d20 (one
    normally, two under advantage/disadvantage) followed by each damage die.
    """

    def __init__(self, script: list[int]) -> None:
        super().__init__()
        self._script = list(script)

    # `a` / `b` mirror the overridden stdlib signature `random.Random.randint(a, b)`.
    def randint(self, a: int, b: int) -> int:  # noqa: WPS111
        return self._script.pop(0)
