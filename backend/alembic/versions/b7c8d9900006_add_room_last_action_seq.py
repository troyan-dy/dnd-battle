"""add room last_action_seq

Revision ID: b7c8d9900006
Revises: a5b6c7800005
Create Date: 2026-06-29 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9900006"
down_revision: str | None = "a5b6c7800005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(
            sa.Column(
                "last_action_seq",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("last_action_seq")
