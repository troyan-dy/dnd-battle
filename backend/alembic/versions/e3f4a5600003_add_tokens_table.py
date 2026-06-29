"""add tokens table

Revision ID: e3f4a5600003
Revises: d2e3f4500002
Create Date: 2026-06-29 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5600003"
down_revision: str | None = "d2e3f4500002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tokens_room_id"), "tokens", ["room_id"], unique=False)
    op.create_index(op.f("ix_tokens_character_id"), "tokens", ["character_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_tokens_character_id"), table_name="tokens")
    op.drop_index(op.f("ix_tokens_room_id"), table_name="tokens")
    op.drop_table("tokens")
