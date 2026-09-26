import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.agent.multi_timeframe import MultiTimeframeDecisionProvider
from ai_spot_trader.domain.enums import MarketType, TradingAction, TradingStyle
from ai_spot_trader.domain.experiments import trading_style_context
from ai_spot_trader.domain.models import (
    AgentInput,
    DecisionCandidate,
    ExecutableMarket,
    ExecutionCostContext,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    market_selection_digest,
)
from ai_spot_trader.market.candles import (
    Candle,
    CandleCache,
    CandleKey,
    CandleStreamService,
    CandleTimeframe,
    floor_time,
)
from ai_spot_trader.market.strategic_context import (
    MAX_STRATEGIC_CONTEXT_BYTES,
    MAX_STRATEGIC_CONTEXT_MARKETS,
    STRATEGIC_HISTORY_DEPTH,
    StrategicContextCapacityError,
    StrategicMultiTimeframeContextService,
)


def _candle(
    *,
    timeframe: CandleTimeframe,
    open_time: datetime,
    close: str = "101",
    is_final: bool = True,
    updated_at: datetime | None = None,
) -> Candle:
    close_time = open_time + timeframe.duration
    return Candle(
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal(close),
        volume=Decimal("3"),
        is_final=is_final,
        updated_at=updated_at or close_time,
    )


class Provider:
    def __init__(self, rows: dict[CandleTimeframe, tuple[Candle, ...]] | None = None) -> None:
        self.rows = rows or {}
        self.calls: list[tuple[CandleTimeframe, int, datetime]] = []

    async def fetch_history(
        self, key: CandleKey, *, limit: int, before: datetime
    ) -> tuple[Candle, ...]:
        self.calls.append((key.timeframe, limit, before))
        return self.rows.get(key.timeframe, ())[-limit:]

    async def _stream(self):
        if False:
            yield None

    def stream(self, key: CandleKey):
        return self._stream()

    async def aclose(self) -> None:
        return None


def test_canonical_style_timeframe_mapping_and_stable_order() -> None:
    assert trading_style_context(TradingStyle.SCALP).preferred_timeframes == (
        "1m",
        "5m",
        "15m",
        "30m",
    )
    assert trading_style_context(TradingStyle.SWING).preferred_timeframes == (
        "1h",
        "4h",
        "1d",
    )


def test_history_as_of_rejects_provider_nonfinal_and_future_rows() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 10, 2, 30, tzinfo=UTC)
        timeframe = CandleTimeframe.M1
        final_open = datetime(2026, 9, 26, 10, 1, tzinfo=UTC)
        active_open = datetime(2026, 9, 26, 10, 2, tzinfo=UTC)
        future_open = datetime(2026, 9, 26, 10, 3, tzinfo=UTC)
        provider = Provider(
            {
                timeframe: (
                    _candle(timeframe=timeframe, open_time=final_open),
                    _candle(
                        timeframe=timeframe,
                        open_time=active_open,
                        is_final=False,
                        updated_at=as_of,
                    ),
                    _candle(timeframe=timeframe, open_time=future_open),
                )
            }
        )
        service = CandleStreamService(provider, cache=CandleCache(max_depth=20))
        key = CandleKey(
            symbol="BTC/USD", market_type=MarketType.SPOT, timeframe=timeframe
        )

        rows = await service.history_as_of(key, as_of=as_of, limit=5)

        assert rows == (_candle(timeframe=timeframe, open_time=final_open),)
        assert provider.calls == [(timeframe, 5, as_of)]
        await service.aclose()

    asyncio.run(scenario())


def test_cached_nonfinal_is_visible_only_if_that_exact_revision_was_known() -> None:
    as_of = datetime(2026, 9, 26, 10, 2, 30, tzinfo=UTC)
    timeframe = CandleTimeframe.M1
    active_open = datetime(2026, 9, 26, 10, 2, tzinfo=UTC)
    key = CandleKey(symbol="BTC/USD", market_type=MarketType.SPOT, timeframe=timeframe)
    cache = CandleCache(max_depth=20)
    causal = _candle(
        timeframe=timeframe,
        open_time=active_open,
        close="100.5",
        is_final=False,
        updated_at=as_of - timedelta(seconds=5),
    )
    cache.upsert(causal, now=as_of)
    assert cache.history_as_of(key, as_of=as_of) == (causal,)

    future_revision = _candle(
        timeframe=timeframe,
        open_time=active_open,
        close="101.5",
        is_final=False,
        updated_at=as_of + timedelta(seconds=5),
    )
    cache.upsert(future_revision, now=as_of + timedelta(seconds=5))
    assert cache.history_as_of(key, as_of=as_of) == ()


def test_builder_marks_partial_missing_stale_and_gaps_without_interpolation() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
        h1 = CandleTimeframe.H1
        d1 = CandleTimeframe.D1
        h1_rows = (
            _candle(timeframe=h1, open_time=datetime(2026, 9, 26, 8, 0, tzinfo=UTC)),
            _candle(timeframe=h1, open_time=datetime(2026, 9, 26, 10, 0, tzinfo=UTC)),
        )
        d1_rows = (
            _candle(timeframe=d1, open_time=datetime(2026, 9, 22, 0, 0, tzinfo=UTC)),
        )
        provider = Provider({h1: h1_rows, CandleTimeframe.H4: (), d1: d1_rows})
        service = CandleStreamService(provider, cache=CandleCache(max_depth=100))
        builder = StrategicMultiTimeframeContextService(service)
        context = await builder.build(
            markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
            trading_style_context=trading_style_context(TradingStyle.SWING),
            as_of=as_of,
        )
        by_tf = {item.timeframe: item for item in context.markets[0].timeframes}

        assert by_tf["1h"].availability == "PARTIAL"
        assert by_tf["1h"].has_gaps is True
        assert by_tf["1h"].gap_count == 1
        assert by_tf["1h"].candle_count == 2
        assert by_tf["4h"].availability == "MISSING"
        assert by_tf["4h"].latest_candle is None
        assert by_tf["1d"].availability == "PARTIAL"
        assert by_tf["1d"].is_stale is True
        assert context.total_candle_count == 3
        assert len(context.model_dump_json().encode("utf-8")) < MAX_STRATEGIC_CONTEXT_BYTES
        await service.aclose()

    asyncio.run(scenario())



def test_builder_keeps_cached_active_candle_explicitly_nonfinal() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 10, 0, 30, tzinfo=UTC)
        timeframe = CandleTimeframe.M1
        boundary = floor_time(as_of, timeframe)
        cache = CandleCache(max_depth=100)
        for index in range(11, 0, -1):
            candle = _candle(
                timeframe=timeframe,
                open_time=boundary - timeframe.duration * index,
            )
            cache.upsert(candle, now=as_of)
        active = _candle(
            timeframe=timeframe,
            open_time=boundary,
            close="100.4",
            is_final=False,
            updated_at=as_of - timedelta(seconds=2),
        )
        cache.upsert(active, now=as_of)
        provider = Provider()
        service = CandleStreamService(provider, cache=cache)
        builder = StrategicMultiTimeframeContextService(service)
        # Build only 1m by using a canonical SCALP context narrowed solely for this service test.
        style = trading_style_context(TradingStyle.SCALP).model_copy(
            update={"preferred_timeframes": ("1m",)}
        )
        context = await builder.build(
            markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
            trading_style_context=style,
            as_of=as_of,
        )
        summary = context.markets[0].timeframes[0]

        assert summary.availability == "AVAILABLE"
        assert summary.latest_candle is not None
        assert summary.latest_candle.is_final is False
        assert summary.latest_candle.updated_at <= as_of
        assert provider.calls == []
        await service.aclose()

    asyncio.run(scenario())


def test_builder_enforces_market_and_serialized_size_bounds() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
        provider = Provider()
        service = CandleStreamService(provider, cache=CandleCache(max_depth=100))
        style = trading_style_context(TradingStyle.SWING)
        markets = tuple(
            ExecutableMarket(symbol=f"A{index:02d}/USD", market_type=MarketType.SPOT)
            for index in range(MAX_STRATEGIC_CONTEXT_MARKETS + 1)
        )
        bounded = StrategicMultiTimeframeContextService(service)
        try:
            await bounded.build(markets=markets, trading_style_context=style, as_of=as_of)
        except StrategicContextCapacityError as exc:
            assert "at most" in str(exc)
        else:
            raise AssertionError("market context bound was not enforced")
        assert provider.calls == []

        tiny = StrategicMultiTimeframeContextService(service, max_serialized_bytes=32)
        try:
            await tiny.build(
                markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
                trading_style_context=style,
                as_of=as_of,
            )
        except StrategicContextCapacityError as exc:
            assert "serialized strategic context" in str(exc)
        else:
            raise AssertionError("serialized context bound was not enforced")
        await service.aclose()

    asyncio.run(scenario())

def test_builder_is_deterministic_bounded_and_serializes_stably() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
        rows: dict[CandleTimeframe, tuple[Candle, ...]] = {}
        for timeframe in (
            CandleTimeframe.M1,
            CandleTimeframe.M5,
            CandleTimeframe.M15,
            CandleTimeframe.M30,
        ):
            depth = STRATEGIC_HISTORY_DEPTH[timeframe]
            boundary = floor_time(as_of, timeframe)
            rows[timeframe] = tuple(
                _candle(
                    timeframe=timeframe,
                    open_time=boundary - timeframe.duration * index,
                )
                for index in range(depth, 0, -1)
            )
        provider = Provider(rows)
        service = CandleStreamService(provider, cache=CandleCache(max_depth=100))
        builder = StrategicMultiTimeframeContextService(service)
        kwargs = dict(
            markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
            trading_style_context=trading_style_context(TradingStyle.SCALP),
            as_of=as_of,
        )
        first = await builder.build(**kwargs)
        second = await builder.build(**kwargs)

        assert first.model_dump_json() == second.model_dump_json()
        assert tuple(item.timeframe for item in first.markets[0].timeframes) == (
            "1m",
            "5m",
            "15m",
            "30m",
        )
        assert all(item.availability == "AVAILABLE" for item in first.markets[0].timeframes)
        # Second build reuses the shared canonical cache when the closed boundary is current.
        assert len(provider.calls) == 4
        await service.aclose()

    asyncio.run(scenario())


class FakeContextService:
    def __init__(self, context) -> None:
        self.context = context
        self.calls = []

    async def build(self, **kwargs):
        self.calls.append(kwargs)
        return self.context


class FakeAgent:
    def __init__(self) -> None:
        self.last_tool_traces = ()
        self.selection_inputs = []
        self.agent_inputs = []

    async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
        self.selection_inputs.append(value)
        selected_at = value.created_at + timedelta(seconds=1)
        selection_id = uuid4()
        market = value.executable_markets[0]
        digest = market_selection_digest(
            selection_id=selection_id,
            cycle_id=value.cycle_id,
            selected_at=selected_at,
            symbol=market.symbol,
            market_type=market.market_type,
            tool_traces=(),
        )
        return MarketSelection(
            selection_id=selection_id,
            cycle_id=value.cycle_id,
            selected_at=selected_at,
            symbol=market.symbol,
            market_type=market.market_type,
            selection_digest=digest,
        )

    async def select_management_market(self, value, **kwargs):
        return await self.select_market(value)

    async def generate_decision(self, value: AgentInput) -> DecisionCandidate:
        self.agent_inputs.append(value)
        return DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=value.cycle_id,
            created_at=value.created_at + timedelta(seconds=1),
            action=TradingAction.HOLD,
            symbol=value.market_state.symbol,
            market_type=value.market_state.market_type,
        )

    async def generate_management_decision(self, value, **kwargs):
        return await self.generate_decision(value)


def test_same_snapshot_reaches_selection_and_final_input_with_costs_preserved() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
        timeframe = CandleTimeframe.H1
        provider = Provider(
            {
                timeframe: tuple(
                    _candle(
                        timeframe=timeframe,
                        open_time=as_of - timeframe.duration * index,
                    )
                    for index in range(STRATEGIC_HISTORY_DEPTH[timeframe], 0, -1)
                ),
                CandleTimeframe.H4: (),
                CandleTimeframe.D1: (),
            }
        )
        candle_service = CandleStreamService(provider, cache=CandleCache(max_depth=100))
        real_context_service = StrategicMultiTimeframeContextService(candle_service)
        style = trading_style_context(TradingStyle.SWING)
        market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
        snapshot = await real_context_service.build(
            markets=(market,), trading_style_context=style, as_of=as_of
        )
        fake_context_service = FakeContextService(snapshot)
        delegate = FakeAgent()
        wrapper = MultiTimeframeDecisionProvider(
            delegate, fake_context_service  # type: ignore[arg-type]
        )
        cycle_id = uuid4()
        portfolio = PortfolioState(portfolio_state_id=uuid4(), as_of=as_of)
        costs = ExecutionCostContext(
            fee_rate=Decimal("0.0025"),
            spread_bps=Decimal("3"),
            slippage_bps=Decimal("2"),
        )
        selection_input = MarketSelectionInput(
            cycle_id=cycle_id,
            created_at=as_of,
            portfolio_state=portfolio,
            executable_markets=(market,),
            aggressiveness=5,
            trading_style_context=style,
            execution_cost_context=costs,
        )
        selection = await wrapper.select_market(selection_input)
        agent_input = AgentInput(
            cycle_id=cycle_id,
            created_at=as_of + timedelta(seconds=2),
            market_state=MarketState(
                market_state_id=uuid4(),
                as_of=as_of + timedelta(seconds=1),
                symbol="BTC/USD",
                last_price=Decimal("101"),
            ),
            portfolio_state=portfolio,
            aggressiveness=5,
            trading_style_context=style,
            execution_cost_context=costs,
            market_selection=selection,
        )
        await wrapper.generate_decision(agent_input)

        assert selection_input.multi_timeframe_context is snapshot
        assert agent_input.multi_timeframe_context is snapshot
        assert agent_input.execution_cost_context == costs
        restored_selection = MarketSelectionInput.model_validate_json(
            selection_input.model_dump_json()
        )
        assert restored_selection.multi_timeframe_context == snapshot
        restored = AgentInput.model_validate_json(agent_input.model_dump_json())
        assert restored.multi_timeframe_context == snapshot
        assert restored.execution_cost_context == costs
        assert len(fake_context_service.calls) == 1
        await candle_service.aclose()

    asyncio.run(scenario())


def test_legacy_input_without_trading_style_does_not_load_multi_timeframe_context() -> None:
    async def scenario() -> None:
        fake_context_service = FakeContextService(None)
        delegate = FakeAgent()
        wrapper = MultiTimeframeDecisionProvider(
            delegate, fake_context_service  # type: ignore[arg-type]
        )
        as_of = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
        cycle_id = uuid4()
        market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
        selection_input = MarketSelectionInput(
            cycle_id=cycle_id,
            created_at=as_of,
            portfolio_state=PortfolioState(portfolio_state_id=uuid4(), as_of=as_of),
            executable_markets=(market,),
            aggressiveness=5,
        )
        await wrapper.select_market(selection_input)
        assert selection_input.multi_timeframe_context is None
        assert fake_context_service.calls == []

    asyncio.run(scenario())
