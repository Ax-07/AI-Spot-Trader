import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

import ai_spot_trader.risk.engine as risk_engine_module
from ai_spot_trader.broker import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    RiskDecision,
    RiskLimit,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    MarketContext,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.risk import InvalidRiskTimeError, RiskEngine, RiskPolicy

NOW = datetime(2026, 9, 20, 16, 0, tzinfo=UTC)
DECISION_AT = NOW - timedelta(seconds=5)
SNAPSHOT_AT = DECISION_AT - timedelta(seconds=1)
CYCLE_ID = UUID("60000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("60000000-0000-0000-0000-000000000002")
RISK_ID = UUID("60000000-0000-0000-0000-000000000003")
EXECUTION_ID = UUID("60000000-0000-0000-0000-000000000004")
MARKET_ID = UUID("60000000-0000-0000-0000-000000000005")
PORTFOLIO_ID = UUID("60000000-0000-0000-0000-000000000006")


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


def cost_model(
    *,
    fee_rate: str = "0",
    spread_bps: str = "0",
    slippage_bps: str = "0",
) -> PaperExecutionCostModel:
    return PaperExecutionCostModel(
        fee_rate=Decimal(fee_rate),
        spread_bps=Decimal(spread_bps),
        slippage_bps=Decimal(slippage_bps),
    )


def engine(
    *,
    policy: RiskPolicy | None = None,
    costs: PaperExecutionCostModel | None = None,
    now: datetime = NOW,
) -> RiskEngine:
    return RiskEngine(
        policy=policy or RiskPolicy(),
        cost_model=costs or cost_model(),
        clock=FixedClock(now),
        risk_assessment_id_factory=lambda: RISK_ID,
        execution_id_factory=lambda: EXECUTION_ID,
    )


def decision(
    action: TradingAction,
    *,
    quantity: str | None = "1",
    symbol: str = "BTC/EUR",
    created_at: datetime = DECISION_AT,
) -> DecisionCandidate:
    proposed = None if action is TradingAction.HOLD else Decimal(quantity or "0")
    return DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=created_at,
        action=action,
        symbol=symbol,
        proposed_quantity=proposed,
    )


def market(
    *,
    price: str = "100",
    symbol: str = "BTC/EUR",
    as_of: datetime = SNAPSHOT_AT,
    last_observed_at: datetime | None = None,
) -> MarketState:
    context = None
    if last_observed_at is not None:
        context = MarketContext(
            last_observed_at=last_observed_at,
            data_age_seconds=Decimal(str((as_of - last_observed_at).total_seconds())),
        )
    return MarketState(
        market_state_id=MARKET_ID,
        as_of=as_of,
        symbol=symbol,
        last_price=Decimal(price),
        context=context,
    )


def portfolio(
    *,
    cash: str | None = "1000",
    btc_quantity: str | None = "2",
    btc_available: str | None = "2",
    as_of: datetime = SNAPSHOT_AT,
) -> PortfolioState:
    balances: tuple[AssetBalance, ...] = ()
    if cash is not None:
        balances = (AssetBalance(asset="EUR", available=Decimal(cash)),)
    positions: tuple[AssetPosition, ...] = ()
    if btc_quantity is not None and btc_available is not None:
        positions = (
            AssetPosition(
                asset="BTC",
                quantity=Decimal(btc_quantity),
                available=Decimal(btc_available),
            ),
        )
    return PortfolioState(
        portfolio_state_id=PORTFOLIO_ID,
        as_of=as_of,
        balances=balances,
        positions=positions,
    )


def test_valid_risk_policy_is_explicit_and_optional() -> None:
    policy = RiskPolicy(
        max_order_notional=Decimal("500"),
        allowed_pairs=frozenset({"BTC/EUR", "ETH/EUR"}),
        stale_after=timedelta(seconds=30),
        allow_quantity_reduction=True,
    )
    assert policy.max_order_notional == Decimal("500")
    assert policy.allowed_pairs == frozenset({"BTC/EUR", "ETH/EUR"})
    assert policy.stale_after == timedelta(seconds=30)
    assert policy.allow_quantity_reduction is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_order_notional": Decimal("0")},
        {"max_order_notional": Decimal("-1")},
        {"max_order_notional": Decimal("NaN")},
        {"max_order_notional": 100},
        {"stale_after": timedelta(0)},
        {"stale_after": timedelta(seconds=-1)},
        {"allowed_pairs": frozenset()},
        {"allowed_pairs": frozenset({"BTCEUR"})},
    ],
)
def test_invalid_risk_policies_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        RiskPolicy(**kwargs)  # type: ignore[arg-type]


def test_risk_engine_has_no_fastapi_kraken_llm_or_paper_broker_dependency() -> None:
    source = inspect.getsource(risk_engine_module)
    assert "fastapi" not in source.lower()
    assert "kraken" not in source.lower()
    assert "llm" not in source.lower()
    assert "PaperBroker" not in source


def test_allow_nominal_buy_produces_correlated_paper_intent() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="2"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.ALLOW
    assert result.assessment.risk_assessment_id == RISK_ID
    assert result.assessment.cycle_id == CYCLE_ID
    assert result.assessment.decision_id == DECISION_ID
    assert result.assessment.requested_quantity == Decimal("2")
    assert result.assessment.authorized_quantity == Decimal("2")
    assert result.assessment.reasons == ()
    assert result.assessment.evaluated_limits == (
        RiskLimit.CANONICAL_SYMBOL,
        RiskLimit.MARKET_SYMBOL,
        RiskLimit.MARKET_CHRONOLOGY,
        RiskLimit.PORTFOLIO_CHRONOLOGY,
        RiskLimit.ASSET_ROLES,
        RiskLimit.QUOTE_BALANCE,
        RiskLimit.BUY_CASH,
    )
    assert result.execution_intent is not None
    assert result.execution_intent.execution_id == EXECUTION_ID
    assert result.execution_intent.risk_assessment_id == RISK_ID
    assert result.execution_intent.quantity == Decimal("2")
    assert result.execution_intent.action is TradingAction.BUY
    assert result.execution_intent.symbol == "BTC/EUR"
    assert result.execution_intent.created_at == NOW
    assert result.execution_intent.mode.value == "PAPER"


def test_allow_nominal_sell() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.SELL, quantity="1.5"),
        market_state=market(),
        portfolio_state=portfolio(btc_quantity="2", btc_available="1.5"),
    )
    assert result.assessment.status is RiskDecision.ALLOW
    assert result.execution_intent is not None
    assert result.execution_intent.quantity == Decimal("1.5")
    assert result.execution_intent.action is TradingAction.SELL


def test_reject_is_explicit_and_never_produces_intent() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="20"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.INSUFFICIENT_CASH,)
    assert result.assessment.authorized_quantity is None
    assert result.execution_intent is None


def test_modify_reduces_quantity_but_never_increases_it() -> None:
    result = engine(policy=RiskPolicy(allow_quantity_reduction=True)).evaluate(
        decision=decision(TradingAction.SELL, quantity="3"),
        market_state=market(),
        portfolio_state=portfolio(btc_quantity="2", btc_available="2"),
    )
    assert result.assessment.status is RiskDecision.MODIFY
    assert result.assessment.requested_quantity == Decimal("3")
    assert result.assessment.authorized_quantity == Decimal("2")
    assert result.assessment.reasons == (RiskReason.SELL_AVAILABLE_LIMIT,)
    assert result.execution_intent is not None
    assert result.execution_intent.quantity == Decimal("2")
    assert result.execution_intent.quantity < Decimal("3")


def test_risk_never_changes_action_or_symbol() -> None:
    result = engine(
        policy=RiskPolicy(max_order_notional=Decimal("50"), allow_quantity_reduction=True)
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(price="100"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.MODIFY
    assert result.execution_intent is not None
    assert result.execution_intent.action is TradingAction.BUY
    assert result.execution_intent.symbol == "BTC/EUR"


def test_buy_cash_check_uses_full_predictable_paper_cost() -> None:
    result = engine(
        costs=cost_model(fee_rate="0.01", spread_bps="100", slippage_bps="100")
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(price="100"),
        portfolio_state=portfolio(cash="102", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.INSUFFICIENT_CASH,)


def test_buy_cash_can_reduce_when_policy_explicitly_allows_it() -> None:
    result = engine(
        policy=RiskPolicy(allow_quantity_reduction=True),
        costs=cost_model(fee_rate="0.01", spread_bps="100", slippage_bps="100"),
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="2"),
        market_state=market(price="100"),
        portfolio_state=portfolio(cash="103.02", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.MODIFY
    assert result.assessment.reasons == (RiskReason.BUY_CASH_LIMIT,)
    assert result.assessment.authorized_quantity == Decimal("1")
    assert result.execution_intent is not None
    assert result.execution_intent.quantity == Decimal("1")


def test_sell_non_held_asset_is_rejected() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.SELL, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(btc_quantity=None, btc_available=None),
    )
    assert result.assessment.reasons == (RiskReason.POSITION_NOT_HELD,)
    assert result.execution_intent is None


def test_sell_above_available_rejects_when_reduction_is_disabled() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.SELL, quantity="1.1"),
        market_state=market(),
        portfolio_state=portfolio(btc_quantity="2", btc_available="1"),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.INSUFFICIENT_POSITION,)


def test_sell_zero_available_rejects_even_when_reduction_is_allowed() -> None:
    result = engine(policy=RiskPolicy(allow_quantity_reduction=True)).evaluate(
        decision=decision(TradingAction.SELL, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(btc_quantity="2", btc_available="0"),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.NO_EXECUTABLE_QUANTITY,)


def test_max_order_notional_rejects_above_limit_and_allows_exact_boundary() -> None:
    policy = RiskPolicy(max_order_notional=Decimal("100"))
    rejected = engine(policy=policy).evaluate(
        decision=decision(TradingAction.BUY, quantity="1.01"),
        market_state=market(price="100"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    allowed = engine(policy=policy).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(price="100"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert rejected.assessment.reasons == (RiskReason.MAX_ORDER_NOTIONAL_EXCEEDED,)
    assert rejected.execution_intent is None
    assert allowed.assessment.status is RiskDecision.ALLOW


def test_max_order_notional_can_reduce_to_exact_limit() -> None:
    result = engine(
        policy=RiskPolicy(
            max_order_notional=Decimal("100"),
            allow_quantity_reduction=True,
        )
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="2"),
        market_state=market(price="80"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.MODIFY
    assert result.assessment.authorized_quantity == Decimal("1.25")
    assert result.assessment.reasons == (RiskReason.MAX_ORDER_NOTIONAL_LIMIT,)


def test_pair_whitelist_is_optional_and_exact_when_configured() -> None:
    unrestricted = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    blocked = engine(policy=RiskPolicy(allowed_pairs=frozenset({"ETH/EUR"}))).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert unrestricted.assessment.status is RiskDecision.ALLOW
    assert blocked.assessment.reasons == (RiskReason.PAIR_NOT_ALLOWED,)


def test_absent_stale_policy_does_not_invent_threshold() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(last_observed_at=NOW - timedelta(days=10)),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.status is RiskDecision.ALLOW


def test_configured_stale_policy_requires_freshness_context() -> None:
    result = engine(policy=RiskPolicy(stale_after=timedelta(seconds=30))).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.reasons == (RiskReason.MARKET_FRESHNESS_UNAVAILABLE,)


def test_stale_boundary_is_strictly_greater_than_threshold() -> None:
    policy = RiskPolicy(stale_after=timedelta(seconds=30))
    exactly = engine(policy=policy).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(last_observed_at=NOW - timedelta(seconds=30)),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    stale = engine(policy=policy).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(last_observed_at=NOW - timedelta(seconds=30, microseconds=1)),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert exactly.assessment.status is RiskDecision.ALLOW
    assert stale.assessment.reasons == (RiskReason.MARKET_DATA_STALE,)


def test_symbol_mismatch_and_invalid_symbol_are_rejected() -> None:
    mismatch = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(symbol="ETH/EUR"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert mismatch.assessment.reasons == (RiskReason.MARKET_SYMBOL_MISMATCH,)

    with pytest.raises(ValidationError):
        decision(TradingAction.BUY, quantity="1", symbol="")

    malformed = decision(TradingAction.BUY, quantity="1", symbol="BTCEUR")
    malformed_result = engine().evaluate(
        decision=malformed,
        market_state=market(symbol="BTCEUR"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert malformed_result.assessment.reasons == (RiskReason.INVALID_SYMBOL,)


def test_base_asset_balance_role_conflict_is_rejected() -> None:
    conflicted = PortfolioState(
        portfolio_state_id=PORTFOLIO_ID,
        as_of=SNAPSHOT_AT,
        balances=(
            AssetBalance(asset="BTC", available=Decimal("1")),
            AssetBalance(asset="EUR", available=Decimal("1000")),
        ),
    )
    buy = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=conflicted,
    )
    sell = engine().evaluate(
        decision=decision(TradingAction.SELL, quantity="1"),
        market_state=market(),
        portfolio_state=conflicted,
    )
    assert buy.assessment.reasons == (RiskReason.ASSET_ROLE_CONFLICT,)
    assert sell.assessment.reasons == (RiskReason.ASSET_ROLE_CONFLICT,)


def test_assessment_records_only_limits_reached_before_rejection() -> None:
    result = engine(
        policy=RiskPolicy(
            allowed_pairs=frozenset({"BTC/EUR"}),
            stale_after=timedelta(seconds=30),
            max_order_notional=Decimal("1000"),
        )
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(symbol="ETH/EUR"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.evaluated_limits == (
        RiskLimit.CANONICAL_SYMBOL,
        RiskLimit.MARKET_SYMBOL,
    )


def test_missing_quote_balance_is_rejected_for_buy_and_sell() -> None:
    buy = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash=None, btc_quantity=None, btc_available=None),
    )
    sell = engine().evaluate(
        decision=decision(TradingAction.SELL, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash=None, btc_quantity="1", btc_available="1"),
    )
    assert buy.assessment.reasons == (RiskReason.QUOTE_BALANCE_MISSING,)
    assert sell.assessment.reasons == (RiskReason.QUOTE_BALANCE_MISSING,)


def test_future_market_or_portfolio_snapshots_are_rejected() -> None:
    future_market = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(as_of=DECISION_AT + timedelta(microseconds=1)),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    future_portfolio = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(
            cash="1000",
            btc_quantity=None,
            btc_available=None,
            as_of=DECISION_AT + timedelta(microseconds=1),
        ),
    )
    assert future_market.assessment.reasons == (RiskReason.FUTURE_MARKET_STATE,)
    assert future_portfolio.assessment.reasons == (RiskReason.FUTURE_PORTFOLIO_STATE,)


def test_assessment_clock_cannot_precede_decision() -> None:
    with pytest.raises(InvalidRiskTimeError):
        engine(now=DECISION_AT - timedelta(microseconds=1)).evaluate(
            decision=decision(TradingAction.BUY, quantity="1"),
            market_state=market(),
            portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
        )


def test_hold_is_allowed_as_strategy_but_never_creates_execution_intent() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.HOLD, quantity=None),
        market_state=market(),
        portfolio_state=portfolio(),
    )
    assert result.assessment.status is RiskDecision.ALLOW
    assert result.assessment.requested_quantity is None
    assert result.assessment.authorized_quantity is None
    assert result.assessment.reasons == (RiskReason.HOLD_NO_EXECUTION,)
    assert result.execution_intent is None


def test_live_remains_structurally_impossible() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.execution_intent is not None
    payload = result.execution_intent.model_dump()
    payload["mode"] = "LIVE"
    with pytest.raises(ValidationError):
        type(result.execution_intent).model_validate(payload)


def test_risk_does_not_mutate_input_snapshots() -> None:
    market_state = market()
    portfolio_state = portfolio(cash="1000", btc_quantity="2", btc_available="2")
    market_before = market_state.model_dump()
    portfolio_before = portfolio_state.model_dump()

    engine(policy=RiskPolicy(allow_quantity_reduction=True)).evaluate(
        decision=decision(TradingAction.SELL, quantity="3"),
        market_state=market_state,
        portfolio_state=portfolio_state,
    )

    assert market_state.model_dump() == market_before
    assert portfolio_state.model_dump() == portfolio_before


def test_same_inputs_and_factories_produce_same_business_result() -> None:
    decision_candidate = decision(TradingAction.BUY, quantity="2")
    market_state = market(price="100")
    portfolio_state = portfolio(cash="150", btc_quantity=None, btc_available=None)
    policy = RiskPolicy(allow_quantity_reduction=True)

    first = engine(policy=policy).evaluate(
        decision=decision_candidate,
        market_state=market_state,
        portfolio_state=portfolio_state,
    )
    second = engine(policy=policy).evaluate(
        decision=decision_candidate,
        market_state=market_state,
        portfolio_state=portfolio_state,
    )
    assert first == second


def test_financial_outputs_remain_decimal() -> None:
    result = engine(
        policy=RiskPolicy(max_order_notional=Decimal("1"), allow_quantity_reduction=True)
    ).evaluate(
        decision=decision(TradingAction.BUY, quantity="1"),
        market_state=market(price="3"),
        portfolio_state=portfolio(cash="1000", btc_quantity=None, btc_available=None),
    )
    assert result.assessment.authorized_quantity is not None
    assert isinstance(result.assessment.authorized_quantity, Decimal)
    assert not isinstance(result.assessment.authorized_quantity, float)
