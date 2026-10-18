"""add is_admin to users

Revision ID: c7d2f4a91b30
Revises: b1f7c2a94d10
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d2f4a91b30"
down_revision = "b1f7c2a94d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts keep working as ordinary users: the server default is false.
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")
