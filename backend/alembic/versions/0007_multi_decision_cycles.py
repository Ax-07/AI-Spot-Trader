"""support ordered multi-decision PAPER cycles

Revision ID: 0007_multi_decision_cycles
Revises: 0006_paper_control_plane
Create Date: 2026-09-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_multi_decision_cycles"
down_revision: str | None = "0006_paper_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing singleton rows become strategic index 0 without losing history.
    op.add_column("audit_decisions", sa.Column("decision_index", sa.Integer(), nullable=True))
    op.execute("UPDATE audit_decisions SET decision_index = 0 WHERE decision_index IS NULL")
    op.alter_column("audit_decisions", "decision_index", nullable=False)

    # These names are PostgreSQL's canonical names for the unnamed UNIQUE constraints created
    # by 0001_audit_journal. Per-decision uniqueness remains on decision_id/risk_assessment_id.
    op.drop_constraint("audit_decisions_cycle_id_key", "audit_decisions", type_="unique")
    op.drop_constraint(
        "audit_risk_assessments_cycle_id_key",
        "audit_risk_assessments",
        type_="unique",
    )
    op.drop_constraint(
        "audit_execution_intents_cycle_id_key",
        "audit_execution_intents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_audit_decisions_cycle_decision_index",
        "audit_decisions",
        ["cycle_id", "decision_index"],
    )

    op.add_column(
        "audit_cycles",
        sa.Column(
            "decision_plan_input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_cycles",
        sa.Column(
            "decision_plan_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_decisions",
        sa.Column(
            "agent_input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_decisions",
        sa.Column(
            "portfolio_after_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Downgrade intentionally fails if the database contains true 1:N cycles, because silently
    # deleting audit facts would violate the journal's immutability contract.
    connection = op.get_bind()
    duplicate_cycle = connection.execute(
        sa.text(
            "SELECT cycle_id FROM audit_decisions GROUP BY cycle_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_cycle is not None:
        raise RuntimeError(
            "cannot downgrade 0007 while multi-decision audit cycles are present"
        )

    op.drop_column("audit_decisions", "portfolio_after_payload")
    op.drop_column("audit_decisions", "agent_input_payload")
    op.drop_column("audit_cycles", "decision_plan_payload")
    op.drop_column("audit_cycles", "decision_plan_input_payload")
    op.drop_constraint(
        "uq_audit_decisions_cycle_decision_index",
        "audit_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "audit_execution_intents_cycle_id_key",
        "audit_execution_intents",
        ["cycle_id"],
    )
    op.create_unique_constraint(
        "audit_risk_assessments_cycle_id_key",
        "audit_risk_assessments",
        ["cycle_id"],
    )
    op.create_unique_constraint(
        "audit_decisions_cycle_id_key",
        "audit_decisions",
        ["cycle_id"],
    )
    op.drop_column("audit_decisions", "decision_index")
