"""add durable PAPER run isolation

Revision ID: 0002_paper_runs
Revises: 0001_audit_journal
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_paper_runs"
down_revision: str | None = "0001_audit_journal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_runs",
        sa.Column("paper_run_id", sa.Uuid(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_type", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_paper_runs_started_at", "paper_runs", ["started_at"])
    op.create_index("ix_paper_runs_ended_at", "paper_runs", ["ended_at"])
    op.create_index("ix_paper_runs_market_type", "paper_runs", ["market_type"])
    op.create_index("ix_paper_runs_symbol", "paper_runs", ["symbol"])

    # Legacy audit rows deliberately remain NULL. Their original run boundaries
    # cannot be reconstructed deterministically and must not be invented.
    op.add_column("audit_cycles", sa.Column("paper_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_audit_cycles_paper_run_id_paper_runs",
        "audit_cycles",
        "paper_runs",
        ["paper_run_id"],
        ["paper_run_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_audit_cycles_paper_run_id", "audit_cycles", ["paper_run_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_cycles_paper_run_id", table_name="audit_cycles")
    op.drop_constraint(
        "fk_audit_cycles_paper_run_id_paper_runs",
        "audit_cycles",
        type_="foreignkey",
    )
    op.drop_column("audit_cycles", "paper_run_id")
    op.drop_table("paper_runs")
