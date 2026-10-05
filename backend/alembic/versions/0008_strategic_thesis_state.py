"""persist strategic position thesis projection

Revision ID: 0008_strategic_thesis_state
Revises: 0007_multi_decision_cycles
Create Date: 2026-10-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_strategic_thesis_state"
down_revision: str | None = "0007_multi_decision_cycles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_cycles",
        sa.Column(
            "strategic_thesis_state_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_cycles", "strategic_thesis_state_payload")
