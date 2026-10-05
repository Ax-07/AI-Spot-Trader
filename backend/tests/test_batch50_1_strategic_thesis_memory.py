from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_spot_trader.agent.planner import STRATEGIC_PLAN_SCHEMA, _plan_input_text
from ai_spot_trader.agent.strategic_thesis import StrategicThesisContextDecisionProvider
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.domain.strategic_thesis import (
    ActiveStrategicThesis,
    StrategicPositionContext,
    StrategicPositionContextEntry,
    StrategicPositionMemoryState,
    StrategicThesisOrigin,
    StrategicThesisReview,
    StrategicThesisStatus,
    StrategicThesisUpdate,
    build_strategic_position_context,
)
from ai_spot_trader.persistence.models import Base, CycleRecord, PaperRunRecord
from ai_spot_trader.persistence.strategic_thesis import (
    derive_committed_active_theses,
    deserialize_active_theses,
    load_latest_active_theses,
    serialize_active_theses,
)
from ai_spot_trader.trading.engine import TradingCycleStatus

NOW = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)
NEXT = NOW + timedelta(minutes=5)
BTC_SPOT = ("BTC/USD", MarketType.SPOT)
BTC_PERP = ("BTC/USD", MarketType.PERPETUAL)
ETH_SPOT = ("ETH/USD", MarketType.SPOT)


def _update(status: StrategicThesisStatus = StrategicThesisStatus.NEW) -> StrategicThesisUpdate:
    return StrategicThesisUpdate(
        status=status,
        horizon="1h-4h",
        thesis_summary="Momentum et structure restent cohérents avec le scénario suivi.",
        supporting_facts=("structure 1h constructive", "flux acheteur présent"),
        invalidation_conditions=("rupture de structure 1h",),
        review_summary=f"revue {status.value.lower()}",
    )


def _spot_market(symbol: str = "BTC/USD", *, at: datetime = NOW) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=at,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.SPOT,
    )


def _perp_market(symbol: str = "BTC/USD", *, at: datetime = NOW) -> MarketState:
    base, quote = symbol.split("/")
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.01"),
        max_position_quantity=Decimal("100"),
        initial_margin_rate=Decimal("0.5"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("2"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketState(
        market_state_id=uuid4(),
        as_of=at,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=at,
            instrument=instrument,
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            funding_rate=Decimal("0"),
        ),
    )


def _portfolio(
    *,
    at: datetime = NOW,
    spot: tuple[tuple[str, str], ...] = (),
    perp: tuple[tuple[str, PositionSide, str], ...] = (),
) -> PortfolioState:
    derivative_positions = []
    for symbol, side, raw_quantity in perp:
        quantity = Decimal(raw_quantity)
        notional = Decimal("100") * quantity
        derivative_positions.append(
            DerivativePosition(
                symbol=symbol,
                side=side,
                quantity=quantity,
                average_entry_price=Decimal("100"),
                mark_price=Decimal("100"),
                mark_observed_at=at,
                contract_size=Decimal("1"),
                notional=notional,
                unrealized_pnl=Decimal("0"),
                leverage=Decimal("2"),
                margin_used=notional / Decimal("2"),
                initial_margin_rate=Decimal("0.5"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=notional * Decimal("0.05"),
            )
        )
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=at,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        positions=tuple(
            AssetPosition(asset=asset, quantity=Decimal(qty), available=Decimal(qty))
            for asset, qty in spot
        ),
        derivative_positions=tuple(derivative_positions),
        cash_available=Decimal("1000"),
    )


def _decision(
    *,
    cycle_id,
    at: datetime,
    action: TradingAction,
    symbol: str = "BTC/USD",
    market_type: MarketType = MarketType.SPOT,
    quantity: Decimal | None = Decimal("1"),
) -> DecisionCandidate:
    return DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=cycle_id,
        created_at=at,
        action=action,
        symbol=symbol,
        market_type=market_type,
        proposed_quantity=None if action is TradingAction.HOLD else quantity,
        rationale="test stratégique",
    )


def _result(
    *,
    before: PortfolioState,
    after: PortfolioState,
    decision: DecisionCandidate,
    update: StrategicThesisUpdate | None,
    filled: bool,
    status: TradingCycleStatus = TradingCycleStatus.COMPLETED,
):
    plan = CycleDecisionPlan(
        cycle_id=decision.cycle_id,
        created_at=decision.created_at,
        decisions=(decision,),
        thesis_updates=(update,),
    )
    fills = (
        (SimpleNamespace(filled_at=decision.created_at + timedelta(seconds=1)),)
        if filled
        else ()
    )
    trajectory = SimpleNamespace(
        decision_index=0,
        decision=decision,
        portfolio_state_before=before,
        portfolio_state_after=after,
        fills=fills,
    )
    return SimpleNamespace(
        status=status,
        decision_plan=plan,
        decision_results=(trajectory,),
    )


def _active_thesis(
    *,
    symbol: str = "BTC/USD",
    market_type: MarketType = MarketType.SPOT,
    side: PositionSide = PositionSide.LONG,
    at: datetime = NOW,
    status: StrategicThesisStatus = StrategicThesisStatus.CONFIRMED,
) -> ActiveStrategicThesis:
    return ActiveStrategicThesis(
        thesis_id=uuid4(),
        symbol=symbol,
        market_type=market_type,
        side=side,
        origin=StrategicThesisOrigin.AGENT_OPENING,
        created_at=at,
        activated_at=at,
        horizon="1h-4h",
        thesis_summary="thèse active",
        supporting_facts=("fait A",),
        invalidation_conditions=("condition B",),
        status=status,
        last_review=StrategicThesisReview(
            reviewed_at=at,
            status=status,
            summary="revue active",
        ),
        updated_at=at,
    )


def test_01_filled_spot_opening_creates_active_thesis() -> None:
    cycle_id = uuid4()
    decision = _decision(cycle_id=cycle_id, at=NOW, action=TradingAction.BUY)
    result = _result(
        before=_portfolio(),
        after=_portfolio(at=NOW + timedelta(seconds=1), spot=(("BTC", "1"),)),
        decision=decision,
        update=_update(),
        filled=True,
    )
    active = derive_committed_active_theses((), result)
    assert len(active) == 1
    assert active[0].origin is StrategicThesisOrigin.AGENT_OPENING
    assert active[0].symbol == "BTC/USD"
    assert active[0].side is PositionSide.LONG


def test_02_rejected_opening_without_economic_position_creates_no_active_thesis() -> None:
    decision = _decision(cycle_id=uuid4(), at=NOW, action=TradingAction.BUY)
    result = _result(
        before=_portfolio(),
        after=_portfolio(),
        decision=decision,
        update=_update(),
        filled=False,
    )
    assert derive_committed_active_theses((), result) == ()


def test_03_intent_without_fill_creates_no_active_thesis() -> None:
    decision = _decision(cycle_id=uuid4(), at=NOW, action=TradingAction.BUY)
    result = _result(
        before=_portfolio(),
        after=_portfolio(),
        decision=decision,
        update=_update(),
        filled=False,
    )
    assert not derive_committed_active_theses((), result)


def test_04_thesis_context_is_reinjected_and_delegate_agent_is_called_once() -> None:
    class Source:
        calls = 0

        async def build_context(self, plan_input):
            self.calls += 1
            return StrategicPositionContext(as_of=plan_input.created_at, positions=())

    class Delegate:
        calls = 0
        last_tool_traces = ()

        async def generate_decision_plan(self, plan_input):
            self.calls += 1
            decision = _decision(
                cycle_id=plan_input.cycle_id,
                at=plan_input.created_at,
                action=TradingAction.HOLD,
                quantity=None,
            )
            return CycleDecisionPlan(
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                decisions=(decision,),
            )

    source = Source()
    delegate = Delegate()
    provider = StrategicThesisContextDecisionProvider(delegate, source)
    plan_input = CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=_portfolio(),
        market_states=(_spot_market(),),
        aggressiveness=5,
    )
    asyncio.run(provider.generate_decision_plan(plan_input))
    assert source.calls == 1
    assert delegate.calls == 1
    assert plan_input.strategic_position_context is not None


def test_05_future_thesis_state_is_rejected_by_causal_context() -> None:
    future = _active_thesis(at=NEXT)
    with pytest.raises(ValidationError, match="postdate"):
        StrategicPositionContext(
            as_of=NOW,
            positions=(
                StrategicPositionContextEntry(
                    symbol="BTC/USD",
                    market_type=MarketType.SPOT,
                    side=PositionSide.LONG,
                    quantity=Decimal("1"),
                    memory_state=StrategicPositionMemoryState.ACTIVE,
                    thesis=future,
                ),
            ),
        )


def test_06_spot_and_perpetual_same_symbol_remain_distinct() -> None:
    spot_thesis = _active_thesis(market_type=MarketType.SPOT)
    perp_thesis = _active_thesis(market_type=MarketType.PERPETUAL)
    context = build_strategic_position_context(
        portfolio_state=_portfolio(
            spot=(("BTC", "1"),),
            perp=(("BTC/USD", PositionSide.LONG, "2"),),
        ),
        market_states=(_perp_market(), _spot_market()),
        active_theses=(perp_thesis, spot_thesis),
        as_of=NOW,
    )
    assert {(item.symbol, item.market_type) for item in context.positions} == {
        BTC_SPOT,
        BTC_PERP,
    }


def test_07_perpetual_long_and_short_are_distinguished_by_thesis_identity() -> None:
    long = _active_thesis(market_type=MarketType.PERPETUAL, side=PositionSide.LONG)
    short = _active_thesis(market_type=MarketType.PERPETUAL, side=PositionSide.SHORT)
    long_context = build_strategic_position_context(
        portfolio_state=_portfolio(perp=(("BTC/USD", PositionSide.LONG, "1"),)),
        market_states=(_perp_market(),),
        active_theses=(long,),
        as_of=NOW,
    )
    short_context = build_strategic_position_context(
        portfolio_state=_portfolio(perp=(("BTC/USD", PositionSide.SHORT, "1"),)),
        market_states=(_perp_market(),),
        active_theses=(short,),
        as_of=NOW,
    )
    assert long_context.positions[0].side is PositionSide.LONG
    assert short_context.positions[0].side is PositionSide.SHORT
    assert long_context.positions[0].thesis.thesis_id != short_context.positions[0].thesis.thesis_id


def test_08_hold_keeps_position_and_updates_thesis_review() -> None:
    previous = (_active_thesis(),)
    decision = _decision(
        cycle_id=uuid4(), at=NEXT, action=TradingAction.HOLD, quantity=None
    )
    result = _result(
        before=_portfolio(at=NEXT, spot=(("BTC", "1"),)),
        after=_portfolio(at=NEXT, spot=(("BTC", "1"),)),
        decision=decision,
        update=_update(StrategicThesisStatus.CONFIRMED),
        filled=False,
    )
    active = derive_committed_active_theses(previous, result)
    assert active[0].thesis_id == previous[0].thesis_id
    assert active[0].last_review.reviewed_at == NEXT


def test_09_augmentation_preserves_thesis_identity_and_updates_review() -> None:
    previous = (_active_thesis(),)
    decision = _decision(cycle_id=uuid4(), at=NEXT, action=TradingAction.BUY)
    result = _result(
        before=_portfolio(at=NEXT, spot=(("BTC", "1"),)),
        after=_portfolio(at=NEXT + timedelta(seconds=1), spot=(("BTC", "2"),)),
        decision=decision,
        update=_update(StrategicThesisStatus.CONFIRMED),
        filled=True,
    )
    active = derive_committed_active_theses(previous, result)
    assert active[0].thesis_id == previous[0].thesis_id
    assert active[0].status is StrategicThesisStatus.CONFIRMED


def test_10_partial_reduction_keeps_active_thesis() -> None:
    previous = (_active_thesis(),)
    decision = _decision(cycle_id=uuid4(), at=NEXT, action=TradingAction.SELL)
    result = _result(
        before=_portfolio(at=NEXT, spot=(("BTC", "2"),)),
        after=_portfolio(at=NEXT + timedelta(seconds=1), spot=(("BTC", "1"),)),
        decision=decision,
        update=_update(StrategicThesisStatus.WEAKENING),
        filled=True,
    )
    active = derive_committed_active_theses(previous, result)
    assert len(active) == 1
    assert active[0].status is StrategicThesisStatus.WEAKENING


def test_11_full_close_retires_active_thesis_but_plan_keeps_final_review() -> None:
    previous = (_active_thesis(),)
    update = _update(StrategicThesisStatus.COMPLETED)
    decision = _decision(cycle_id=uuid4(), at=NEXT, action=TradingAction.SELL)
    result = _result(
        before=_portfolio(at=NEXT, spot=(("BTC", "1"),)),
        after=_portfolio(at=NEXT + timedelta(seconds=1)),
        decision=decision,
        update=update,
        filled=True,
    )
    assert derive_committed_active_theses(previous, result) == ()
    assert result.decision_plan.thesis_updates == (update,)


def test_12_recovery_follows_explicit_paper_run_lineage() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        parent_id = uuid4()
        child_id = uuid4()
        thesis = _active_thesis()
        async with sessions.begin() as session:
            session.add_all(
                [
                    PaperRunRecord(
                        paper_run_id=parent_id,
                        started_at=NOW,
                        execution_universe_payload=[],
                    ),
                    PaperRunRecord(
                        paper_run_id=child_id,
                        started_at=NEXT,
                        execution_universe_payload=[],
                        resumed_from_paper_run_id=parent_id,
                    ),
                    CycleRecord(
                        cycle_id=uuid4(),
                        paper_run_id=parent_id,
                        status=TradingCycleStatus.COMPLETED.value,
                        recorded_at=NOW,
                        result_digest="0" * 64,
                        strategic_thesis_state_payload=serialize_active_theses((thesis,)),
                    ),
                ]
            )
        async with sessions() as session:
            recovered = await load_latest_active_theses(session, child_id)
        assert recovered == (thesis,)
        await engine.dispose()

    asyncio.run(scenario())


def test_13_legacy_position_without_snapshot_is_explicitly_unavailable() -> None:
    context = build_strategic_position_context(
        portfolio_state=_portfolio(spot=(("BTC", "1"),)),
        market_states=(_spot_market(),),
        active_theses=(),
        as_of=NOW,
    )
    assert context.positions[0].memory_state is StrategicPositionMemoryState.UNAVAILABLE_LEGACY
    assert context.positions[0].thesis is None


def test_14_failed_cycle_does_not_mutate_durable_thesis_projection() -> None:
    previous = (_active_thesis(),)
    failed = SimpleNamespace(
        status=TradingCycleStatus.FAILED,
        decision_plan=None,
        decision_results=(),
    )
    assert derive_committed_active_theses(previous, failed) == previous


def test_15_multiple_decisions_update_distinct_theses_in_order() -> None:
    cycle_id = uuid4()
    btc = _decision(cycle_id=cycle_id, at=NOW, action=TradingAction.BUY)
    eth = _decision(
        cycle_id=cycle_id,
        at=NOW,
        action=TradingAction.BUY,
        symbol="ETH/USD",
    )
    plan = CycleDecisionPlan(
        cycle_id=cycle_id,
        created_at=NOW,
        decisions=(btc, eth),
        thesis_updates=(_update(), _update()),
    )
    trajectories = (
        SimpleNamespace(
            decision_index=0,
            decision=btc,
            portfolio_state_before=_portfolio(),
            portfolio_state_after=_portfolio(
                at=NOW + timedelta(seconds=1), spot=(("BTC", "1"),)
            ),
            fills=(SimpleNamespace(filled_at=NOW + timedelta(seconds=1)),),
        ),
        SimpleNamespace(
            decision_index=1,
            decision=eth,
            portfolio_state_before=_portfolio(
                at=NOW + timedelta(seconds=1), spot=(("BTC", "1"),)
            ),
            portfolio_state_after=_portfolio(
                at=NOW + timedelta(seconds=2),
                spot=(("BTC", "1"), ("ETH", "1")),
            ),
            fills=(SimpleNamespace(filled_at=NOW + timedelta(seconds=2)),),
        ),
    )
    result = SimpleNamespace(
        status=TradingCycleStatus.COMPLETED,
        decision_plan=plan,
        decision_results=trajectories,
    )
    active = derive_committed_active_theses((), result)
    assert {(item.symbol, item.market_type) for item in active} == {BTC_SPOT, ETH_SPOT}


def test_16_agent_wrapper_has_no_second_strategic_call_path() -> None:
    source = inspect.getsource(StrategicThesisContextDecisionProvider.generate_decision_plan)
    assert source.count("generate_decision_plan") == 2  # method declaration + one delegate call
    assert "await self._delegate.generate_decision_plan(plan_input)" in source


def test_17_thesis_modules_do_not_import_risk_or_broker_execution() -> None:
    import ai_spot_trader.agent.strategic_thesis as agent_module
    import ai_spot_trader.persistence.strategic_thesis as persistence_module

    combined = inspect.getsource(agent_module) + inspect.getsource(persistence_module)
    assert "ai_spot_trader.risk" not in combined
    assert "ai_spot_trader.broker" not in combined


def test_18_thesis_snapshot_serialization_round_trip_is_stable() -> None:
    original = (
        _active_thesis(),
        _active_thesis(
            symbol="ETH/USD",
            market_type=MarketType.PERPETUAL,
            side=PositionSide.SHORT,
        ),
    )
    payload = serialize_active_theses(original)
    assert payload == serialize_active_theses(original)
    assert deserialize_active_theses(payload) == tuple(
        sorted(original, key=lambda item: (item.market_type.value, item.symbol, item.side.value))
    )
    assert [item["symbol"] for item in payload] == ["ETH/USD", "BTC/USD"]


def test_19_plan_input_rejects_strategic_context_outside_market_universe() -> None:
    context = build_strategic_position_context(
        portfolio_state=_portfolio(spot=(("ETH", "1"),)),
        market_states=(_spot_market("ETH/USD"),),
        active_theses=(),
        as_of=NOW,
    )
    with pytest.raises(ValidationError, match="inside market_states"):
        CycleDecisionPlanInput(
            cycle_id=uuid4(),
            created_at=NOW,
            portfolio_state=_portfolio(spot=(("ETH", "1"),)),
            market_states=(_spot_market("BTC/USD"),),
            aggressiveness=5,
            strategic_position_context=context,
        )


def test_20_old_plans_without_thesis_updates_remain_compatible() -> None:
    cycle_id = uuid4()
    decision = _decision(
        cycle_id=cycle_id, at=NOW, action=TradingAction.HOLD, quantity=None
    )
    plan = CycleDecisionPlan(
        cycle_id=cycle_id,
        created_at=NOW,
        decisions=(decision,),
    )
    assert plan.thesis_updates == ()


def test_21_prompt_contract_makes_invalidated_non_automatic() -> None:
    plan_input = CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=_portfolio(),
        market_states=(_spot_market(),),
        aggressiveness=5,
    )
    rendered = _plan_input_text(plan_input)
    assert "INVALIDATED" in rendered
    assert "jamais des ordres SELL automatiques" in rendered
    assert "chaîne de pensée cachée" in rendered


def test_22_structured_output_schema_requires_thesis_update_per_decision() -> None:
    variants = STRATEGIC_PLAN_SCHEMA["properties"]["decisions"]["items"]["anyOf"]
    assert all("thesis_update" in item["required"] for item in variants)
    assert all("thesis_update" in item["properties"] for item in variants)
