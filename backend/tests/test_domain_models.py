from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ai_spot_trader.domain.enums import ExecutionMode, RiskDecision, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketContext,
    MarketObservation,
    MarketState,
    MarketWindowStats,
    PortfolioState,
    RiskAssessment,
)

NOW = datetime(2026, 9, 20, 10, 30, tzinfo=UTC)


def make_market_state() -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/EUR",
        last_price=Decimal("50000.00"),
    )


def make_portfolio_state() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
        positions=(
            AssetPosition(
                asset="BTC",
                quantity=Decimal("0.10"),
                available=Decimal("0.08"),
            ),
        ),
    )


def test_valid_domain_contracts_and_enums() -> None:
    cycle_id = uuid4()
    decision_id = uuid4()
    risk_assessment_id = uuid4()
    market_state = make_market_state()
    portfolio_state = make_portfolio_state()

    agent_input = AgentInput(
        cycle_id=cycle_id,
        created_at=NOW,
        market_state=market_state,
        portfolio_state=portfolio_state,
        aggressiveness=6,
    )
    decision = DecisionCandidate(
        decision_id=decision_id,
        cycle_id=cycle_id,
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/EUR",
        rationale="Test decision",
    )
    risk = RiskAssessment(
        risk_assessment_id=risk_assessment_id,
        cycle_id=cycle_id,
        decision_id=decision_id,
        assessed_at=NOW,
        status=RiskDecision.ALLOW,
    )
    intent = ExecutionIntent(
        execution_id=uuid4(),
        cycle_id=cycle_id,
        decision_id=decision_id,
        risk_assessment_id=risk_assessment_id,
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/EUR",
        quantity=Decimal("0.01"),
    )
    fill = Fill(
        fill_id=uuid4(),
        execution_id=intent.execution_id,
        filled_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/EUR",
        quantity=Decimal("0.01"),
        price=Decimal("50010.00"),
    )

    assert agent_input.aggressiveness == 6
    assert decision.action is TradingAction.BUY
    assert "\"action\":\"BUY\"" in decision.model_dump_json()
    assert risk.status is RiskDecision.ALLOW
    assert intent.mode is ExecutionMode.PAPER
    assert fill.quantity == Decimal("0.01")


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=uuid4(),
            created_at=NOW,
            action="WAIT",  # type: ignore[arg-type]
            symbol="BTC/EUR",
        )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketState(
            market_state_id=uuid4(),
            as_of=datetime(2026, 9, 20, 10, 30),
            symbol="BTC/EUR",
            last_price=Decimal("50000"),
        )


def test_non_utc_aware_timestamp_is_normalized_to_utc() -> None:
    source = datetime(2026, 9, 20, 12, 30, tzinfo=timezone(timedelta(hours=2)))

    market_state = MarketState(
        market_state_id=uuid4(),
        as_of=source,
        symbol="BTC/EUR",
        last_price=Decimal("50000"),
    )

    assert market_state.as_of.tzinfo is UTC
    assert market_state.as_of == NOW


@pytest.mark.parametrize("field_name", ["quantity", "available"])
def test_negative_position_quantities_are_rejected(field_name: str) -> None:
    values = {
        "asset": "BTC",
        "quantity": Decimal("1"),
        "available": Decimal("1"),
    }
    values[field_name] = Decimal("-0.01")

    with pytest.raises(ValidationError):
        AssetPosition.model_validate(values)


def test_available_position_cannot_exceed_held_quantity() -> None:
    with pytest.raises(ValidationError):
        AssetPosition(
            asset="BTC",
            quantity=Decimal("0.5"),
            available=Decimal("0.6"),
        )


def test_domain_models_reject_wrong_python_types() -> None:
    with pytest.raises(ValidationError):
        MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/EUR",
            last_price="50000",  # type: ignore[arg-type]
        )


def test_execution_intent_rejects_hold_and_non_positive_quantity() -> None:
    base = {
        "execution_id": uuid4(),
        "cycle_id": uuid4(),
        "decision_id": uuid4(),
        "risk_assessment_id": uuid4(),
        "created_at": NOW,
        "symbol": "BTC/EUR",
    }

    with pytest.raises(ValidationError):
        ExecutionIntent(**base, action=TradingAction.HOLD, quantity=Decimal("1"))

    with pytest.raises(ValidationError):
        ExecutionIntent(**base, action=TradingAction.BUY, quantity=Decimal("0"))


def test_fill_rejects_hold() -> None:
    with pytest.raises(ValidationError):
        Fill(
            fill_id=uuid4(),
            execution_id=uuid4(),
            filled_at=NOW,
            action=TradingAction.HOLD,
            symbol="BTC/EUR",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )


def test_json_round_trip_preserves_contract() -> None:
    market_state = make_market_state()
    payload = market_state.model_dump_json()
    restored = MarketState.model_validate_json(payload)

    assert restored == market_state
    assert isinstance(restored.market_state_id, UUID)
    assert restored.as_of.tzinfo is UTC


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketState.model_validate(
            {
                "market_state_id": uuid4(),
                "as_of": NOW,
                "symbol": "BTC/EUR",
                "last_price": Decimal("50000"),
                "unexpected": True,
            }
        )


def test_market_observation_requires_positive_price_and_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        MarketObservation(
            observed_at=datetime(2026, 9, 20, 10, 30),
            symbol="BTC/EUR",
            last_price=Decimal("1"),
        )
    with pytest.raises(ValidationError):
        MarketObservation(observed_at=NOW, symbol="BTC/EUR", last_price=Decimal("0"))


def test_market_window_rejects_fake_statistics_for_empty_history() -> None:
    with pytest.raises(ValidationError):
        MarketWindowStats(
            horizon_seconds=Decimal("300"),
            window_start=NOW - timedelta(minutes=5),
            observation_count=0,
            is_complete=False,
            min_price=Decimal("1"),
        )


def test_market_context_requires_consistent_stale_evaluation() -> None:
    with pytest.raises(ValidationError):
        MarketContext(
            last_observed_at=NOW,
            data_age_seconds=Decimal("11"),
            stale_after_seconds=Decimal("10"),
            is_stale=False,
        )


def test_market_state_rejects_future_context_observation() -> None:
    context = MarketContext(
        last_observed_at=NOW + timedelta(seconds=1),
        data_age_seconds=Decimal("0"),
    )
    with pytest.raises(ValidationError):
        MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/EUR",
            last_price=Decimal("50000"),
            context=context,
        )
