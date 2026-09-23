"""add PAPER control plane strategies, campaigns and run linkage

Revision ID: 0006_paper_control_plane
Revises: 0005_paper_run_recovery
Create Date: 2026-09-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_paper_control_plane"
down_revision: str | None = "0005_paper_run_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("strategy_id"),
    )
    op.create_index("ix_strategies_strategy_name", "strategies", ["strategy_name"])
    op.create_index("ix_strategies_created_at", "strategies", ["created_at"])
    op.create_index("ix_strategies_archived_at", "strategies", ["archived_at"])

    op.create_table(
        "strategy_revisions",
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_revision", sa.Integer(), nullable=False),
        sa.Column("strategy_prompt", sa.Text(), nullable=False),
        sa.Column("strategy_prompt_digest", sa.String(length=64), nullable=False),
        sa.Column("base_agent_contract_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.strategy_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("strategy_id", "strategy_revision"),
    )
    op.create_index(
        "ix_strategy_revisions_strategy_prompt_digest",
        "strategy_revisions",
        ["strategy_prompt_digest"],
    )
    op.create_index(
        "ix_strategy_revisions_created_at",
        "strategy_revisions",
        ["created_at"],
    )

    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_revision", sa.Integer(), nullable=False),
        sa.Column("strategy_prompt_digest", sa.String(length=64), nullable=False),
        sa.Column("base_agent_contract_version", sa.String(length=64), nullable=False),
        sa.Column(
            "configuration_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("configuration_digest", sa.String(length=64), nullable=False),
        sa.Column("experiment_protocol_version", sa.String(length=64), nullable=False),
        sa.Column("experiment_digest", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id", "strategy_revision"],
            ["strategy_revisions.strategy_id", "strategy_revisions.strategy_revision"],
            name="fk_campaigns_strategy_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index("ix_campaigns_created_at", "campaigns", ["created_at"])
    op.create_index("ix_campaigns_strategy_id", "campaigns", ["strategy_id"])
    op.create_index(
        "ix_campaigns_configuration_digest",
        "campaigns",
        ["configuration_digest"],
    )
    op.create_index(
        "ix_campaigns_experiment_digest",
        "campaigns",
        ["experiment_digest"],
    )

    op.add_column("paper_runs", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_paper_runs_campaign_id",
        "paper_runs",
        "campaigns",
        ["campaign_id"],
        ["campaign_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_paper_runs_campaign_id", "paper_runs", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_runs_campaign_id", table_name="paper_runs")
    op.drop_constraint("fk_paper_runs_campaign_id", "paper_runs", type_="foreignkey")
    op.drop_column("paper_runs", "campaign_id")

    op.drop_index("ix_campaigns_experiment_digest", table_name="campaigns")
    op.drop_index("ix_campaigns_configuration_digest", table_name="campaigns")
    op.drop_index("ix_campaigns_strategy_id", table_name="campaigns")
    op.drop_index("ix_campaigns_created_at", table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_index("ix_strategy_revisions_created_at", table_name="strategy_revisions")
    op.drop_index(
        "ix_strategy_revisions_strategy_prompt_digest", table_name="strategy_revisions"
    )
    op.drop_table("strategy_revisions")

    op.drop_index("ix_strategies_archived_at", table_name="strategies")
    op.drop_index("ix_strategies_created_at", table_name="strategies")
    op.drop_index("ix_strategies_strategy_name", table_name="strategies")
    op.drop_table("strategies")
