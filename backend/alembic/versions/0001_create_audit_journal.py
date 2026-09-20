"""create durable PAPER audit journal

Revision ID: 0001_audit_journal
Revises:
Create Date: 2026-09-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_audit_journal"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_cycles",
        sa.Column("cycle_id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("failure_stage", sa.String(length=32)),
        sa.Column("failure_error_type", sa.String(length=255)),
        sa.Column("failure_timed_out", sa.Boolean()),
        sa.Column("market_state_id", sa.Uuid()),
        sa.Column("portfolio_state_before_id", sa.Uuid()),
        sa.Column("portfolio_state_after_id", sa.Uuid()),
        sa.Column("market_as_of", sa.DateTime(timezone=True)),
        sa.Column("portfolio_before_as_of", sa.DateTime(timezone=True)),
        sa.Column("portfolio_after_as_of", sa.DateTime(timezone=True)),
        sa.Column("agent_input_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("portfolio_after_payload", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.create_index("ix_audit_cycles_status", "audit_cycles", ["status"])
    op.create_index("ix_audit_cycles_recorded_at", "audit_cycles", ["recorded_at"])
    op.create_index("ix_audit_cycles_market_state_id", "audit_cycles", ["market_state_id"])
    op.create_index(
        "ix_audit_cycles_portfolio_state_before_id",
        "audit_cycles",
        ["portfolio_state_before_id"],
    )
    op.create_index(
        "ix_audit_cycles_portfolio_state_after_id",
        "audit_cycles",
        ["portfolio_state_after_id"],
    )
    op.create_index("ix_audit_cycles_market_as_of", "audit_cycles", ["market_as_of"])

    op.create_table(
        "audit_decisions",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_audit_decisions_cycle_id", "audit_decisions", ["cycle_id"])
    op.create_index("ix_audit_decisions_action", "audit_decisions", ["action"])
    op.create_index("ix_audit_decisions_symbol", "audit_decisions", ["symbol"])

    op.create_table(
        "audit_risk_assessments",
        sa.Column("risk_assessment_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "decision_id",
            sa.Uuid(),
            sa.ForeignKey("audit_decisions.decision_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_audit_risk_assessments_cycle_id", "audit_risk_assessments", ["cycle_id"]
    )
    op.create_index(
        "ix_audit_risk_assessments_decision_id",
        "audit_risk_assessments",
        ["decision_id"],
    )
    op.create_index("ix_audit_risk_assessments_status", "audit_risk_assessments", ["status"])

    op.create_table(
        "audit_execution_intents",
        sa.Column("execution_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "decision_id",
            sa.Uuid(),
            sa.ForeignKey("audit_decisions.decision_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "risk_assessment_id",
            sa.Uuid(),
            sa.ForeignKey("audit_risk_assessments.risk_assessment_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_audit_execution_intents_cycle_id", "audit_execution_intents", ["cycle_id"]
    )
    op.create_index(
        "ix_audit_execution_intents_decision_id", "audit_execution_intents", ["decision_id"]
    )
    op.create_index(
        "ix_audit_execution_intents_risk_assessment_id",
        "audit_execution_intents",
        ["risk_assessment_id"],
    )

    op.create_table(
        "audit_fills",
        sa.Column("fill_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "execution_id",
            sa.Uuid(),
            sa.ForeignKey("audit_execution_intents.execution_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_state_id", sa.Uuid(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_audit_fills_execution_id", "audit_fills", ["execution_id"])
    op.create_index("ix_audit_fills_market_state_id", "audit_fills", ["market_state_id"])
    op.create_index("ix_audit_fills_filled_at", "audit_fills", ["filled_at"])


def downgrade() -> None:
    op.drop_table("audit_fills")
    op.drop_table("audit_execution_intents")
    op.drop_table("audit_risk_assessments")
    op.drop_table("audit_decisions")
    op.drop_table("audit_cycles")
