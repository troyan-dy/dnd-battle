"""add token hidden (fog of war)

Revision ID: c8d9ea00aa07
Revises: b7c8d9900006
Create Date: 2026-06-29 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9ea00aa07"
down_revision: str | None = "b7c8d9900006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tokens") as batch:
        batch.add_column(
            sa.Column(
                "hidden",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tokens") as batch:
        batch.drop_column("hidden")
