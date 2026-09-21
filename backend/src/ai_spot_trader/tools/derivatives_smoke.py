from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from pydantic import SecretStr

from ai_spot_trader.analytics.paper import PaperAnalyticsReport
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.core.clock import SystemClock
from ai_spot_trader.core.config import PaperRunConfiguration, Settings
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarginMode,
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DecisionCandidate,
    DerivativePosition,
    PortfolioState,
)
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesMarketDataSource,
    KrakenDerivativesPublicClient,
)
from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner, RunBoundCycleAuditWriter
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import AuditSortOrder, SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
from ai_spot_trader.persistence.runs import (
    PaperRunSortOrder,
    SqlAlchemyPaperRunLifecycle,
    SqlAlchemyPaperRunQueryService,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.trading.engine import (
    TradingCycleResult,
    TradingCycleRunner,
    TradingCycleStatus,
    TradingCycleTimeouts,
)

_DEFAULT_SYMBOL = "BTC/USD"
_DEFAULT_VENUE_SYMBOL = "PF_XBTUSD"
_DEFAULT_MAX_SMOKE_NOTIONAL = Decimal("50")


class SmokeSafetyError(RuntimeError):
    """Raised when a controlled smoke would leave its deliberately narrow safety envelope."""


class SmokeValidationError(RuntimeError):
    """Raised when the canonical pipeline does not produce the expected smoke artefacts."""


class SmokeSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class SmokeStepKind(StrEnum):
    OPEN = "open"
    MARK = "mark"
    REDUCE = "reduce"
    CLOSE_OVERSIZE = "close_oversize"


@dataclass(frozen=True, slots=True)
class SmokeStep:
    kind: SmokeStepKind
    action: TradingAction
    quantity_multiplier: Decimal | None


@dataclass(slots=True)
class DerivativesSmokeRuntime:
    database: Database
    market_data: KrakenDerivativesMarketDataSource
    portfolio: PaperPortfolioLedger
    lifecycle: SqlAlchemyPaperRunLifecycle
    run_reader: SqlAlchemyPaperRunQueryService
    audit_reader: SqlAlchemyCycleAuditQueryService
    analytics_reader: SqlAlchemyPaperAnalyticsQueryService
    runner: AuditedTradingCycleRunner


class ScriptedSmokeDecisionProvider:
    """Test-only LLMProvider double used exclusively by the Batch 16.3 CLI harness."""

    def __init__(
        self,
        *,
        plan: tuple[SmokeStep, ...],
        max_smoke_notional: Decimal,
    ) -> None:
        if not plan:
            raise ValueError("smoke plan cannot be empty")
        if max_smoke_notional <= 0:
            raise ValueError("max_smoke_notional must be positive")
        self._plan = plan
        self._max_smoke_notional = max_smoke_notional
        self._index = 0

    @property
    def remaining_steps(self) -> int:
        return len(self._plan) - self._index

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        if self._index >= len(self._plan):
            raise SmokeSafetyError("scripted smoke plan is exhausted")

        market = agent_input.market_state
        context = market.derivative
        if market.market_type is not MarketType.PERPETUAL or context is None:
            raise SmokeSafetyError("Batch 16.3 smoke accepts PERPETUAL market data only")
        instrument = context.instrument
        if instrument.contract_kind is not DerivativeContractKind.LINEAR:
            raise SmokeSafetyError("Batch 16.3 smoke accepts linear perpetuals only")
        if market.symbol != _DEFAULT_SYMBOL or instrument.venue_symbol != _DEFAULT_VENUE_SYMBOL:
            raise SmokeSafetyError(
                "Batch 16.3 smoke is pinned to BTC/USD / PF_XBTUSD"
            )

        step = self._plan[self._index]
        proposed_quantity: Decimal | None = None
        if step.quantity_multiplier is not None:
            proposed_quantity = instrument.min_order_quantity * step.quantity_multiplier
            reference_notional = (
                context.mark_price * proposed_quantity * instrument.contract_size
            )
            if reference_notional > self._max_smoke_notional:
                raise SmokeSafetyError(
                    "smoke reference notional exceeds the configured smoke safety cap"
                )

        self._index += 1
        return DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=agent_input.cycle_id,
            created_at=agent_input.created_at,
            action=step.action,
            symbol=market.symbol,
            proposed_quantity=proposed_quantity,
            rationale=(
                "CONTROLLED_SMOKE_BATCH_16_3: "
                f"{step.kind.value}; deterministic validation decision, not agent strategy"
            ),
            market_type=MarketType.PERPETUAL,
        )


def build_smoke_plan(side: SmokeSide) -> tuple[SmokeStep, ...]:
    if side is SmokeSide.LONG:
        opening = TradingAction.BUY
        closing = TradingAction.SELL
    else:
        opening = TradingAction.SELL
        closing = TradingAction.BUY
    return (
        SmokeStep(SmokeStepKind.OPEN, opening, Decimal("2")),
        SmokeStep(SmokeStepKind.MARK, TradingAction.HOLD, None),
        SmokeStep(SmokeStepKind.REDUCE, closing, Decimal("1")),
        SmokeStep(SmokeStepKind.CLOSE_OVERSIZE, closing, Decimal("2")),
    )


def validate_smoke_configuration(run: PaperRunConfiguration) -> None:
    if run.market_type is not MarketType.PERPETUAL:
        raise SmokeSafetyError("set AI_SPOT_TRADER_PAPER_MARKET_TYPE=PERPETUAL")
    if run.symbol != _DEFAULT_SYMBOL:
        raise SmokeSafetyError("Batch 16.3 smoke is pinned to BTC/USD")
    if run.settlement_asset != "USD":
        raise SmokeSafetyError("Batch 16.3 BTC/USD smoke requires USD settlement")
    if run.derivative_margin_mode is not MarginMode.ISOLATED:
        raise SmokeSafetyError("Batch 16.3 smoke requires ISOLATED margin")
    if run.derivative_leverage != Decimal(1):
        raise SmokeSafetyError("Batch 16.3 smoke requires leverage exactly 1")
    if not run.allow_quantity_reduction:
        raise SmokeSafetyError(
            "Batch 16.3 close-oversize validation requires risk quantity reduction enabled"
        )


def build_derivatives_smoke_runtime(
    settings: Settings,
    *,
    side: SmokeSide,
    max_smoke_notional: Decimal,
) -> DerivativesSmokeRuntime:
    """Compose a test-only process from canonical PAPER components without OpenAI execution."""

    if settings.environment == "production":
        raise SmokeSafetyError("Batch 16.3 controlled smoke is forbidden in production")
    run = PaperRunConfiguration.from_settings(settings)
    validate_smoke_configuration(run)
    clock = SystemClock()

    database = Database(run.database_url.get_secret_value())
    audit_repository = SqlAlchemyCycleAuditRepository(database.sessions)
    audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
    analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
    lifecycle = SqlAlchemyPaperRunLifecycle(
        database.sessions,
        market_type=run.market_type.value,
        symbol=run.symbol,
        clock=clock,
    )
    run_reader = SqlAlchemyPaperRunQueryService(database.sessions)

    portfolio = PaperPortfolioLedger(
        initial_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=clock.now(),
            balances=(
                AssetBalance(
                    asset=run.settlement_asset,
                    available=run.initial_capital,
                ),
            ),
        ),
        clock=clock,
    )
    market_data = KrakenDerivativesMarketDataSource(
        KrakenDerivativesPublicClient(
            settings.kraken_derivatives_rest_url,
            timeout_seconds=settings.kraken_rest_timeout_seconds,
        ),
        clock=clock,
        market_sink=portfolio,
        stale_after=(
            timedelta(seconds=settings.kraken_stale_after_seconds)
            if settings.kraken_stale_after_seconds is not None
            else None
        ),
    )
    cost_model = PaperExecutionCostModel(
        fee_rate=run.fee_rate,
        spread_bps=run.spread_bps,
        slippage_bps=run.slippage_bps,
    )
    risk_engine = RiskEngine(
        policy=RiskPolicy(
            max_order_notional=run.max_order_notional,
            allowed_pairs=run.allowed_pairs,
            allow_quantity_reduction=run.allow_quantity_reduction,
            derivative_leverage=run.derivative_leverage or Decimal(1),
            max_derivative_leverage=run.max_derivative_leverage or Decimal(1),
            max_derivative_position_notional=run.max_derivative_position_notional,
            max_total_derivative_exposure=run.max_total_derivative_exposure,
            derivative_liquidation_buffer_ratio=(
                run.derivative_liquidation_buffer_ratio or Decimal("1.10")
            ),
            derivative_margin_mode=run.derivative_margin_mode,
        ),
        cost_model=cost_model,
        clock=clock,
    )
    broker = PaperBroker(ledger=portfolio, cost_model=cost_model, clock=clock)
    scripted_provider = ScriptedSmokeDecisionProvider(
        plan=build_smoke_plan(side),
        max_smoke_notional=max_smoke_notional,
    )
    cycle_runner = TradingCycleRunner(
        market_data=market_data,
        portfolio=portfolio,
        agent=scripted_provider,
        risk_engine=risk_engine,
        broker=broker,
        symbol=run.symbol,
        aggressiveness=run.aggressiveness,
        timeouts=TradingCycleTimeouts(
            market_seconds=run.market_timeout_seconds,
            agent_seconds=run.agent_timeout_seconds,
            broker_seconds=run.broker_timeout_seconds,
        ),
        clock=clock,
    )
    run_bound_writer = RunBoundCycleAuditWriter(
        delegate=audit_repository,
        run_provider=lifecycle,
    )
    runner = AuditedTradingCycleRunner(
        delegate=cycle_runner,
        audit_writer=run_bound_writer,
    )
    return DerivativesSmokeRuntime(
        database=database,
        market_data=market_data,
        portfolio=portfolio,
        lifecycle=lifecycle,
        run_reader=run_reader,
        audit_reader=audit_reader,
        analytics_reader=analytics_reader,
        runner=runner,
    )


async def run_controlled_smoke(
    settings: Settings,
    *,
    side: SmokeSide,
    max_smoke_notional: Decimal,
    funding_wait_seconds: float,
    allow_open_ended_runs: bool,
) -> dict[str, object]:
    if funding_wait_seconds < 0:
        raise ValueError("funding_wait_seconds cannot be negative")

    runtime = build_derivatives_smoke_runtime(
        settings,
        side=side,
        max_smoke_notional=max_smoke_notional,
    )
    run_id: UUID | None = None
    payload: dict[str, object] | None = None
    try:
        existing = await runtime.run_reader.list_runs(
            limit=100,
            offset=0,
            order=PaperRunSortOrder.DESC,
        )
        open_ended = tuple(item for item in existing.items if item.ended_at is None)
        if open_ended and not allow_open_ended_runs:
            ids = ", ".join(str(item.paper_run_id) for item in open_ended)
            raise SmokeSafetyError(
                "open-ended PAPER runs exist; stop the backend cleanly or pass "
                f"--allow-open-ended-runs after reviewing them: {ids}"
            )

        started = await runtime.lifecycle.initialize()
        run_id = started.paper_run_id
        initial_portfolio = runtime.portfolio.snapshot()
        plan = build_smoke_plan(side)
        results: list[TradingCycleResult] = []

        for step in plan:
            if step.kind is SmokeStepKind.MARK and funding_wait_seconds > 0:
                await asyncio.sleep(funding_wait_seconds)
            result = await runtime.runner.run_cycle()
            _validate_cycle(step=step, side=side, result=result, runtime=runtime)
            results.append(result)

        cycles = await runtime.audit_reader.list_cycles_for_run(
            run_id,
            limit=20,
            offset=0,
            order=AuditSortOrder.ASC,
        )
        executions = await runtime.audit_reader.list_executions_for_run(
            run_id,
            limit=20,
            offset=0,
            order=AuditSortOrder.ASC,
        )
        if cycles.total != len(plan):
            raise SmokeValidationError(
                f"expected {len(plan)} durable cycles, found {cycles.total}"
            )
        if executions.total != 3:
            raise SmokeValidationError(
                f"expected 3 durable executions, found {executions.total}"
            )

        analytics = await runtime.analytics_reader.paper_analytics_for_run(run_id)
        hold_result = results[1]
        marked_position = _single_position_from_input(hold_result)
        final_portfolio = runtime.portfolio.snapshot()
        payload = {
            "batch": "16.3",
            "mode": "CONTROLLED_PERPETUAL_PAPER_SMOKE",
            "side": side.value,
            "paper_run_id": str(run_id),
            "symbol": _DEFAULT_SYMBOL,
            "venue_symbol": _DEFAULT_VENUE_SYMBOL,
            "initial_portfolio": initial_portfolio.model_dump(mode="json"),
            "cycles": [_cycle_payload(result) for result in results],
            "mark_observation": {
                "mark_price": str(marked_position.mark_price),
                "unrealized_pnl": str(marked_position.unrealized_pnl),
                "cumulative_funding": str(marked_position.cumulative_funding),
                "funding_observed": marked_position.cumulative_funding != 0,
            },
            "final_portfolio": final_portfolio.model_dump(mode="json"),
            "durable_audit": {
                "cycle_count": cycles.total,
                "execution_count": executions.total,
                "cycle_ids": [str(item.cycle_id) for item in cycles.items],
            },
            "analytics": _analytics_payload(analytics),
        }
    finally:
        try:
            await runtime.lifecycle.close()
            if payload is not None and run_id is not None:
                closed_run = await runtime.run_reader.get_run(run_id)
                if closed_run is None or closed_run.ended_at is None:
                    raise SmokeValidationError("smoke PAPER run did not close durably")
                payload["paper_run_ended_at"] = closed_run.ended_at.isoformat()
        finally:
            try:
                await runtime.market_data.aclose()
            finally:
                await runtime.database.close()

    if payload is None or run_id is None:
        raise SmokeValidationError("smoke ended before producing a report")
    return payload


async def verify_run_isolation(
    settings: Settings,
    *,
    first_run_id: UUID,
    second_run_id: UUID,
) -> dict[str, object]:
    if first_run_id == second_run_id:
        raise SmokeValidationError("isolation verification requires two distinct run IDs")
    database = Database(_database_url(settings.database_url))
    try:
        run_reader = SqlAlchemyPaperRunQueryService(database.sessions)
        audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
        analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
        entries: list[dict[str, object]] = []
        cycle_sets: list[set[UUID]] = []
        for run_id in (first_run_id, second_run_id):
            run = await run_reader.get_run(run_id)
            if run is None:
                raise SmokeValidationError(f"paper run {run_id} does not exist")
            if run.market_type != MarketType.PERPETUAL.value or run.symbol != _DEFAULT_SYMBOL:
                raise SmokeValidationError(f"paper run {run_id} is not a BTC/USD PERPETUAL run")
            cycles = await audit_reader.list_cycles_for_run(
                run_id,
                limit=100,
                offset=0,
                order=AuditSortOrder.ASC,
            )
            if cycles.total == 0:
                raise SmokeValidationError(f"paper run {run_id} has no durable cycles")
            ids = {item.cycle_id for item in cycles.items}
            cycle_sets.append(ids)
            analytics = await analytics_reader.paper_analytics_for_run(run_id)
            entries.append(
                {
                    "paper_run_id": str(run_id),
                    "started_at": run.started_at.isoformat(),
                    "ended_at": None if run.ended_at is None else run.ended_at.isoformat(),
                    "cycle_count": cycles.total,
                    "cycle_ids": [str(value) for value in sorted(ids, key=str)],
                    "analytics": _analytics_payload(analytics),
                }
            )
        overlap = cycle_sets[0] & cycle_sets[1]
        if overlap:
            joined = ", ".join(str(value) for value in sorted(overlap, key=str))
            raise SmokeValidationError(f"run-scoped cycle overlap detected: {joined}")
        return {
            "batch": "16.3",
            "isolation_verified": True,
            "runs": entries,
        }
    finally:
        await database.close()


def _validate_cycle(
    *,
    step: SmokeStep,
    side: SmokeSide,
    result: TradingCycleResult,
    runtime: DerivativesSmokeRuntime,
) -> None:
    if result.status is not TradingCycleStatus.COMPLETED:
        failure = None if result.failure is None else result.failure.error_type
        raise SmokeValidationError(f"{step.kind.value} cycle failed: {failure}")
    if result.decision is None or result.risk_assessment is None:
        raise SmokeValidationError(f"{step.kind.value} cycle lacks decision/Risk artefacts")
    if result.decision.action is not step.action:
        raise SmokeValidationError(f"{step.kind.value} decision action mismatch")

    assessment = result.risk_assessment
    intent = result.execution_intent
    positions = runtime.portfolio.snapshot().derivative_positions
    market = result.agent_input.market_state if result.agent_input is not None else None
    if market is None or market.derivative is None:
        raise SmokeValidationError(f"{step.kind.value} cycle lacks derivative market context")
    minimum = market.derivative.instrument.min_order_quantity

    if step.kind is SmokeStepKind.MARK:
        if assessment.status is not RiskDecision.ALLOW or intent is not None or result.fills:
            raise SmokeValidationError("MARK/HOLD cycle must be ALLOW without execution")
        _single_position(positions)
        return

    if intent is None or len(result.fills) != 1:
        raise SmokeValidationError(f"{step.kind.value} must produce one execution fill")

    expected_side = PositionSide.LONG if side is SmokeSide.LONG else PositionSide.SHORT
    if step.kind is SmokeStepKind.OPEN:
        if assessment.status is not RiskDecision.ALLOW:
            raise SmokeValidationError("OPEN must be accepted unchanged by Risk")
        if intent.reduce_only:
            raise SmokeValidationError("OPEN intent cannot be reduce_only")
        if intent.quantity != minimum * Decimal("2"):
            raise SmokeValidationError("OPEN quantity differs from 2x Kraken minimum")
        position = _single_position(positions)
        if position.side is not expected_side or position.quantity != intent.quantity:
            raise SmokeValidationError("OPEN did not create the expected derivative position")
        return

    if not intent.reduce_only:
        raise SmokeValidationError(f"{step.kind.value} intent must be reduce_only")
    if step.kind is SmokeStepKind.REDUCE:
        if assessment.status is not RiskDecision.ALLOW:
            raise SmokeValidationError("REDUCE at exact quantity must be ALLOW")
        if intent.quantity != minimum:
            raise SmokeValidationError("REDUCE quantity differs from Kraken minimum")
        position = _single_position(positions)
        if position.side is not expected_side or position.quantity != minimum:
            raise SmokeValidationError("REDUCE did not leave exactly one minimum unit")
        return

    if assessment.status is not RiskDecision.MODIFY:
        raise SmokeValidationError("CLOSE_OVERSIZE must be modified by Risk")
    if RiskReason.DERIVATIVE_REDUCE_ONLY_LIMIT not in assessment.reasons:
        raise SmokeValidationError("CLOSE_OVERSIZE lacks DERIVATIVE_REDUCE_ONLY_LIMIT")
    if intent.quantity != minimum:
        raise SmokeValidationError("CLOSE_OVERSIZE was not clamped to the remaining position")
    if positions:
        raise SmokeValidationError("CLOSE_OVERSIZE must close without reversing the position")


def _single_position_from_input(result: TradingCycleResult) -> DerivativePosition:
    if result.agent_input is None:
        raise SmokeValidationError("cycle lacks AgentInput")
    return _single_position(result.agent_input.portfolio_state.derivative_positions)


def _single_position(
    positions: tuple[DerivativePosition, ...],
) -> DerivativePosition:
    if len(positions) != 1:
        raise SmokeValidationError(
            f"expected exactly one derivative position, found {len(positions)}"
        )
    return positions[0]


def _cycle_payload(result: TradingCycleResult) -> dict[str, object]:
    return {
        "cycle_id": str(result.cycle_id),
        "status": result.status.value,
        "failure": (
            None
            if result.failure is None
            else {
                "stage": result.failure.stage.value,
                "error_type": result.failure.error_type,
                "timed_out": result.failure.timed_out,
            }
        ),
        "market_type": (
            None
            if result.agent_input is None
            else result.agent_input.market_state.market_type.value
        ),
        "symbol": None if result.decision is None else result.decision.symbol,
        "decision": None if result.decision is None else result.decision.model_dump(mode="json"),
        "risk": (
            None
            if result.risk_assessment is None
            else result.risk_assessment.model_dump(mode="json")
        ),
        "intent": (
            None
            if result.execution_intent is None
            else result.execution_intent.model_dump(mode="json")
        ),
        "fills": [fill.model_dump(mode="json") for fill in result.fills],
        "portfolio_before": (
            None
            if result.agent_input is None
            else result.agent_input.portfolio_state.model_dump(mode="json")
        ),
        "portfolio_after": (
            None
            if result.portfolio_state_after is None
            else result.portfolio_state_after.model_dump(mode="json")
        ),
    }


def _analytics_payload(report: PaperAnalyticsReport) -> dict[str, object]:
    return {
        "calculation_version": report.calculation_version,
        "source_digest": report.source_digest,
        "summary": asdict(report.summary),
        "point_count": len(report.points),
    }


def _database_url(value: SecretStr | None) -> str:
    if value is None or not value.get_secret_value().strip():
        raise SmokeSafetyError("AI_SPOT_TRADER_DATABASE_URL is required")
    url = value.get_secret_value().strip()
    if not url.startswith("postgresql+asyncpg://"):
        raise SmokeSafetyError("Batch 16.3 isolation verification requires PostgreSQL/asyncpg")
    return url


def _positive_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("expected a decimal value") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite decimal")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a numeric value") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative value")
    return parsed


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a UUID") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch 16.3 controlled Kraken PERPETUAL PAPER smoke harness. "
            "This tool is not imported by the normal FastAPI composition."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="execute one controlled LONG or SHORT PAPER run")
    run.add_argument("--side", choices=tuple(side.value for side in SmokeSide), required=True)
    run.add_argument(
        "--max-smoke-notional",
        type=_positive_decimal,
        default=_DEFAULT_MAX_SMOKE_NOTIONAL,
        help="hard reference-notional cap for every scripted executable decision (default: 50)",
    )
    run.add_argument(
        "--funding-wait-seconds",
        type=_non_negative_float,
        default=5.0,
        help="delay before the HOLD mark/funding cycle; zero disables the wait",
    )
    run.add_argument(
        "--allow-open-ended-runs",
        action="store_true",
        help="allow a new smoke despite older paper_runs rows with ended_at=NULL",
    )

    verify = subparsers.add_parser(
        "verify-isolation",
        help="verify that two durable PAPER runs have disjoint run-scoped cycles/analytics",
    )
    verify.add_argument("--first-run-id", type=_uuid, required=True)
    verify.add_argument("--second-run-id", type=_uuid, required=True)
    return parser


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, UUID)):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    command = cast(str, args.command)
    if command == "run":
        payload = asyncio.run(
            run_controlled_smoke(
                settings,
                side=SmokeSide(cast(str, args.side)),
                max_smoke_notional=cast(Decimal, args.max_smoke_notional),
                funding_wait_seconds=cast(float, args.funding_wait_seconds),
                allow_open_ended_runs=cast(bool, args.allow_open_ended_runs),
            )
        )
    else:
        payload = asyncio.run(
            verify_run_isolation(
                settings,
                first_run_id=cast(UUID, args.first_run_id),
                second_run_id=cast(UUID, args.second_run_id),
            )
        )
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
