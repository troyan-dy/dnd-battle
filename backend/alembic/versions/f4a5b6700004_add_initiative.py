"""add initiative tracker (room turn pointer + initiative_entries)

Revision ID: f4a5b6700004
Revises: e3f4a5600003
Create Date: 2026-06-29 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6700004"
down_revision: str | None = "e3f4a5600003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("initiative_active_index", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "initiative_round",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    op.create_table(
        "initiative_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("initiative", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
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
    op.create_index(
        op.f("ix_initiative_entries_room_id"), "initiative_entries", ["room_id"], unique=False
    )
    op.create_index(
        op.f("ix_initiative_entries_character_id"),
        "initiative_entries",
        ["character_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_initiative_entries_character_id"), table_name="initiative_entries")
    op.drop_index(op.f("ix_initiative_entries_room_id"), table_name="initiative_entries")
    op.drop_table("initiative_entries")

    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("initiative_round")
        batch.drop_column("initiative_active_index")
