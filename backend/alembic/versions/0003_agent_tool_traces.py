"""persist Agent read-only tool traces at cycle level

Revision ID: 0003_agent_tool_traces
Revises: 0002_paper_runs
Create Date: 2026-09-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_agent_tool_traces"
down_revision: str | None = "0002_paper_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable preserves every legacy row exactly as recorded. New code writes a
    # normalized JSON array, including [] when no research tool was used.
    op.add_column(
        "audit_cycles",
        sa.Column(
            "agent_tool_traces_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_cycles", "agent_tool_traces_payload")
