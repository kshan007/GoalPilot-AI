"""add admin audit log

Revision ID: d8e3a5b02c41
Revises: c7d2f4a91b30
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d8e3a5b02c41"
down_revision = "c7d2f4a91b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("target_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_created", "admin_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
