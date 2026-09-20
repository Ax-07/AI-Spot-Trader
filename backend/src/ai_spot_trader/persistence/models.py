from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """SQLAlchemy metadata root for the durable audit journal."""


class CycleRecord(Base):
    __tablename__ = "audit_cycles"

    cycle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
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
    agent_input_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    portfolio_after_payload: Mapped[dict[str, object] | None] = mapped_column(JsonType)

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
