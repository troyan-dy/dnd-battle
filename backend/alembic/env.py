"""Alembic migration environment (async-aware).

Reads the connection URL from :data:`app.config.DATABASE_URL` and uses the
project's ``Base.metadata`` (with every model imported) as the autogenerate
target. Works for both Postgres (asyncpg) and sqlite (aiosqlite).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from app import models
from app.config import DATABASE_URL
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to the script output without a live DB connection."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Open an async engine and run migrations within a connection."""
    connectable = async_engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
