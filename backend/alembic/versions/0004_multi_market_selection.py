"""add multi-market PAPER universe and causal market selection

Revision ID: 0004_multi_market_selection
Revises: 0003_agent_tool_traces
Create Date: 2026-09-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_multi_market_selection"
down_revision: str | None = "0003_agent_tool_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_runs",
        sa.Column(
            "execution_universe_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    # Existing runs are truthful single-market experiments. Backfill the typed universe from
    # their original durable fields before allowing those legacy columns to become nullable.
    op.execute(
        """
        UPDATE paper_runs
        SET execution_universe_payload = jsonb_build_array(
            jsonb_build_object('symbol', symbol, 'market_type', market_type)
        )
        WHERE execution_universe_payload IS NULL
        """
    )
    op.alter_column("paper_runs", "execution_universe_payload", nullable=False)
    op.alter_column("paper_runs", "market_type", existing_type=sa.String(length=16), nullable=True)
    op.alter_column("paper_runs", "symbol", existing_type=sa.String(length=64), nullable=True)

    op.add_column(
        "audit_cycles",
        sa.Column(
            "market_selection_input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_cycles",
        sa.Column(
            "market_selection_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    multi_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM paper_runs "
            "WHERE market_type IS NULL OR symbol IS NULL"
        )
    ).scalar_one()
    if multi_count:
        raise RuntimeError(
            "cannot downgrade 0004 while multi-market PAPER runs exist; "
            "legacy market_type/symbol cannot represent them truthfully"
        )

    op.drop_column("audit_cycles", "market_selection_payload")
    op.drop_column("audit_cycles", "market_selection_input_payload")
    op.alter_column("paper_runs", "symbol", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("paper_runs", "market_type", existing_type=sa.String(length=16), nullable=False)
    op.drop_column("paper_runs", "execution_universe_payload")
