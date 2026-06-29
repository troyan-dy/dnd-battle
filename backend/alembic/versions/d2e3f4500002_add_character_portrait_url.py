"""add character portrait_url

Revision ID: d2e3f4500002
Revises: c1d2e3f40001
Create Date: 2026-06-29 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4500002"
down_revision: str | None = "c1d2e3f40001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("portrait_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_column("portrait_url")
