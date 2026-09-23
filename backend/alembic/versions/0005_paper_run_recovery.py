"""add durable PAPER restart recovery metadata

Revision ID: 0005_paper_run_recovery
Revises: 0004_multi_market_selection
Create Date: 2026-09-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_paper_run_recovery"
down_revision: str | None = "0004_multi_market_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_runs",
        sa.Column("resumed_from_paper_run_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "paper_runs",
        sa.Column("recovery_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "paper_runs",
        sa.Column(
            "initial_portfolio_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "paper_runs",
        sa.Column(
            "current_portfolio_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_paper_runs_resumed_from_paper_run_id",
        "paper_runs",
        "paper_runs",
        ["resumed_from_paper_run_id"],
        ["paper_run_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_paper_runs_resumed_from_paper_run_id",
        "paper_runs",
        ["resumed_from_paper_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_paper_runs_resumed_from_paper_run_id",
        table_name="paper_runs",
    )
    op.drop_constraint(
        "fk_paper_runs_resumed_from_paper_run_id",
        "paper_runs",
        type_="foreignkey",
    )
    op.drop_column("paper_runs", "current_portfolio_payload")
    op.drop_column("paper_runs", "initial_portfolio_payload")
    op.drop_column("paper_runs", "recovery_version")
    op.drop_column("paper_runs", "resumed_from_paper_run_id")
