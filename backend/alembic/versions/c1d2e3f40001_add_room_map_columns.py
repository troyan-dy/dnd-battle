"""add room map columns

Revision ID: c1d2e3f40001
Revises: b6c7e100aa86
Create Date: 2026-06-29 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f40001"
down_revision: str | None = "b6c7e100aa86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rooms", schema=None) as batch_op:
        batch_op.add_column(sa.Column("map_image_path", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("map_content_type", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rooms", schema=None) as batch_op:
        batch_op.drop_column("map_content_type")
        batch_op.drop_column("map_image_path")
