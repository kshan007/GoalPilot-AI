"""add recommendation_runs

Additive only: one new table, no column is dropped, renamed or retyped, and no existing row is
touched. On SQLite the table is also created by ``Base.metadata.create_all`` at startup, so an
existing local database gains the table without any manual step.

Revision ID: b1f7c2a94d10
Revises: 903315a72db4
Create Date: 2026-10-17 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1f7c2a94d10"
down_revision: Union[str, None] = "903315a72db4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("optimization_run_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("runtime_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["optimization_run_id"], ["optimization_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_runs_user_id", "recommendation_runs", ["user_id"], unique=False
    )
    op.create_index(
        "ix_recommendations_user_created",
        "recommendation_runs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_user_created", table_name="recommendation_runs")
    op.drop_index("ix_recommendation_runs_user_id", table_name="recommendation_runs")
    op.drop_table("recommendation_runs")
