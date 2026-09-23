from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """SQLAlchemy metadata root for durable PAPER state and audit records."""


class StrategyRecord(Base):
    __tablename__ = "strategies"

    strategy_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    revisions: Mapped[list["StrategyRevisionRecord"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyRevisionRecord.strategy_revision",
    )


class StrategyRevisionRecord(Base):
    __tablename__ = "strategy_revisions"

    strategy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    strategy_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_prompt_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_agent_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    strategy: Mapped[StrategyRecord] = relationship(back_populates="revisions")


class CampaignRecord(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_id", "strategy_revision"],
            ["strategy_revisions.strategy_id", "strategy_revisions.strategy_revision"],
            ondelete="RESTRICT",
            name="fk_campaigns_strategy_revision",
        ),
    )

    campaign_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    strategy_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    strategy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_prompt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    base_agent_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False)
    configuration_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    experiment_protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    paper_runs: Mapped[list["PaperRunRecord"]] = relationship(back_populates="campaign")


class PaperRunRecord(Base):
    __tablename__ = "paper_runs"

    paper_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    campaign_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaigns.campaign_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # Legacy singleton projection. Multi-market Batch 18.2 runs deliberately keep these NULL
    # rather than inventing a fake MULTI symbol/type.
    market_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    execution_universe_payload: Mapped[list[dict[str, object]]] = mapped_column(
        JsonType, nullable=False
    )
    # Batch 18.6 keeps one run per backend lifetime, but records an explicit predecessor and the
    # exact starting ledger snapshot so restart recovery never depends on replaying Agent output.
    resumed_from_paper_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("paper_runs.paper_run_id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
        index=True,
    )
    recovery_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_portfolio_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    current_portfolio_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)

    campaign: Mapped[CampaignRecord | None] = relationship(back_populates="paper_runs")
    cycles: Mapped[list["CycleRecord"]] = relationship(back_populates="paper_run")


class CycleRecord(Base):
    __tablename__ = "audit_cycles"

    cycle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    paper_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("paper_runs.paper_run_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_stage: Mapped[str | None] = mapped_column(String(32))
    failure_error_type: Mapped[str | None] = mapped_column(String(255))
    failure_timed_out: Mapped[bool | None] = mapped_column(Boolean)
    market_state_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    portfolio_state_before_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    portfolio_state_after_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    market_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    portfolio_before_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    portfolio_after_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    market_selection_input_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    market_selection_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    agent_input_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    agent_tool_traces_payload: Mapped[list[dict[str, object]] | None] = mapped_column(JsonType)
    portfolio_after_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)

    paper_run: Mapped[PaperRunRecord | None] = relationship(back_populates="cycles")
    decision: Mapped["DecisionRecord | None"] = relationship(
        back_populates="cycle",
        cascade="all, delete-orphan",
        uselist=False,
    )
    risk_assessment: Mapped["RiskAssessmentRecord | None"] = relationship(
        back_populates="cycle",
        cascade="all, delete-orphan",
        uselist=False,
    )
    execution_intent: Mapped["ExecutionIntentRecord | None"] = relationship(
        back_populates="cycle",
        cascade="all, delete-orphan",
        uselist=False,
    )


class DecisionRecord(Base):
    __tablename__ = "audit_decisions"

    decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    cycle_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False)

    cycle: Mapped[CycleRecord] = relationship(back_populates="decision")
    risk_assessment: Mapped["RiskAssessmentRecord | None"] = relationship(
        back_populates="decision",
        uselist=False,
    )


class RiskAssessmentRecord(Base):
    __tablename__ = "audit_risk_assessments"

    risk_assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    cycle_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False)

    cycle: Mapped[CycleRecord] = relationship(back_populates="risk_assessment")
    decision: Mapped[DecisionRecord] = relationship(back_populates="risk_assessment")
    execution_intent: Mapped["ExecutionIntentRecord | None"] = relationship(
        back_populates="risk_assessment",
        uselist=False,
    )


class ExecutionIntentRecord(Base):
    __tablename__ = "audit_execution_intents"

    execution_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    cycle_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_cycles.cycle_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    risk_assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_risk_assessments.risk_assessment_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False)

    cycle: Mapped[CycleRecord] = relationship(back_populates="execution_intent")
    risk_assessment: Mapped[RiskAssessmentRecord] = relationship(
        back_populates="execution_intent"
    )
    fills: Mapped[list["FillRecord"]] = relationship(
        back_populates="execution_intent",
        cascade="all, delete-orphan",
    )


class FillRecord(Base):
    __tablename__ = "audit_fills"

    fill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_execution_intents.execution_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_state_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False)

    execution_intent: Mapped[ExecutionIntentRecord] = relationship(back_populates="fills")
