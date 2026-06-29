"""Runtime configuration sourced from environment variables.

Kept deliberately tiny (stdlib only) so importing models/migrations never
requires a running database or extra settings dependency. The async SQLAlchemy
URL defaults to a local sqlite file so tests and offline tooling work without
Postgres; production/dev set ``DATABASE_URL`` to the asyncpg Postgres URL
(see ``.env.example``).
"""

import os

# Async driver URL. Postgres in real deployments; sqlite+aiosqlite as a
# zero-infra default for unit tests and local schema tooling.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./dnd_battle.db",
)
