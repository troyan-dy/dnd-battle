"""add character armor_class + resistances

Revision ID: a5b6c7800005
Revises: f4a5b6700004
Create Date: 2026-06-29 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7800005"
down_revision: str | None = "f4a5b6700004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch:
        batch.add_column(
            sa.Column(
                "armor_class",
                sa.Integer(),
                nullable=False,
                server_default="10",
            )
        )
        batch.add_column(
            sa.Column(
                "resistances",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("characters") as batch:
        batch.drop_column("resistances")
        batch.drop_column("armor_class")
