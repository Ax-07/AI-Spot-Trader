import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, ExecutionMode, MarketType
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DerivativeInstrument,
    MarketObservation,
    PortfolioState,
)
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesMarketDataSource,
    KrakenDerivativesPublicClient,
    parse_kraken_derivatives_mark_candles,
)
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, StaleMarketDataError

NOW = datetime(2026, 9, 22, 0, 30, tzinfo=UTC)
TICKER_AT = NOW - timedelta(seconds=2)

INSTRUMENT = DerivativeInstrument(
    symbol="BTC/USD",
    venue_symbol="PF_XBTUSD",
    market_type=MarketType.PERPETUAL,
    contract_kind=DerivativeContractKind.LINEAR,
    underlying_asset="BTC",
    quote_asset="USD",
    contract_size=Decimal("1"),
    tick_size=Decimal("1"),
    min_order_quantity=Decimal("0.0001"),
    max_position_quantity=Decimal("1000"),
    initial_margin_rate=Decimal("0.1"),
    maintenance_margin_rate=Decimal("0.05"),
    max_leverage=Decimal("10"),
    funding_interval_seconds=Decimal("3600"),
)


class FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeDerivativesRest:
    def __init__(
        self,
        *,
        ticker_at: datetime = TICKER_AT,
        mark_price: Decimal = Decimal("65000"),
        history: tuple[MarketObservation, ...] | None = None,
    ) -> None:
        self.ticker_at = ticker_at
        self.mark_price = mark_price
        self.history = history if history is not None else mark_history()
        self.history_calls: list[tuple[datetime, datetime]] = []
        self.closed = False

    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]:
        return (INSTRUMENT,)

    async def fetch_ticker(
        self,
        instrument: DerivativeInstrument,
    ) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]:
        assert instrument == INSTRUMENT
        return self.ticker_at, self.mark_price, Decimal("64990"), Decimal("0.0001")

    async def fetch_mark_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[MarketObservation, ...]:
        assert instrument == INSTRUMENT
        self.history_calls.append((since, until))
        return self.history

    async def aclose(self) -> None:
        self.closed = True


def mark_history() -> tuple[MarketObservation, ...]:
    observations: list[MarketObservation] = []
    for minutes_ago in range(32, 0, -1):
        observations.append(
            MarketObservation(
                observed_at=NOW - timedelta(minutes=minutes_ago),
                symbol="BTC/USD",
                last_price=Decimal(65000 + (32 - minutes_ago) * 10),
            )
        )
    return tuple(observations)


def test_perpetual_snapshot_reuses_canonical_market_context_builder() -> None:
    rest = FakeDerivativesRest()
    source = KrakenDerivativesMarketDataSource(
        rest,
        clock=FixedClock(),
        stale_after=timedelta(seconds=10),
    )

    state = asyncio.run(source.snapshot("BTC/USD"))

    assert state.market_type is MarketType.PERPETUAL
    assert state.last_price == Decimal("65000")
    assert state.context is not None
    assert state.context.last_observed_at == TICKER_AT
    assert state.context.data_age_seconds == Decimal("2")
    assert state.context.is_stale is False
    assert [window.horizon_seconds for window in state.context.windows] == [
        Decimal("300"),
        Decimal("1800"),
    ]
    assert all(window.is_complete for window in state.context.windows)
    assert all(window.return_fraction is not None for window in state.context.windows)
    assert all(window.realized_volatility is not None for window in state.context.windows)
    assert state.derivative is not None
    assert state.derivative.instrument == INSTRUMENT
    assert state.derivative.mark_price == Decimal("65000")
    assert state.derivative.index_price == Decimal("64990")
    assert state.derivative.funding_rate == Decimal("0.0001")

    assert len(rest.history_calls) == 1
    since, until = rest.history_calls[0]
    assert since == TICKER_AT - timedelta(minutes=32)
    assert until == TICKER_AT


def test_perpetual_context_excludes_non_closed_or_future_history_without_lookahead() -> None:
    history = mark_history() + (
        MarketObservation(
            observed_at=TICKER_AT,
            symbol="BTC/USD",
            last_price=Decimal("999999"),
        ),
        MarketObservation(
            observed_at=TICKER_AT + timedelta(minutes=1),
            symbol="BTC/USD",
            last_price=Decimal("888888"),
        ),
    )
    source = KrakenDerivativesMarketDataSource(
        FakeDerivativesRest(history=history),
        clock=FixedClock(),
    )

    state = asyncio.run(source.snapshot("BTC/USD"))

    assert state.context is not None
    assert all(
        window.max_price is None or window.max_price < Decimal("999999")
        for window in state.context.windows
    )
    assert state.last_price == Decimal("65000")


def test_repeated_identical_perpetual_snapshot_is_statistically_deterministic() -> None:
    rest = FakeDerivativesRest()
    source = KrakenDerivativesMarketDataSource(rest, clock=FixedClock())

    first = asyncio.run(source.snapshot("BTC/USD"))
    second = asyncio.run(source.snapshot("BTC/USD"))

    assert first.context is not None and second.context is not None
    assert first.context.windows == second.context.windows
    assert first.context.last_observed_at == second.context.last_observed_at == TICKER_AT
    assert len(rest.history_calls) == 2


def test_perpetual_context_is_serializable_inside_agent_input() -> None:
    source = KrakenDerivativesMarketDataSource(FakeDerivativesRest(), clock=FixedClock())
    state = asyncio.run(source.snapshot("BTC/USD"))
    agent_input = AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=state,
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            mode=ExecutionMode.PAPER,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        aggressiveness=2,
    )

    payload = json.loads(agent_input.model_dump_json())

    context = payload["market_state"]["context"]
    assert context is not None
    assert len(context["windows"]) == 2
    assert context["windows"][0]["return_fraction"] is not None
    derivative = payload["market_state"]["derivative"]
    assert derivative["instrument"]["venue_symbol"] == "PF_XBTUSD"
    assert derivative["mark_price"] == "65000"
    assert derivative["index_price"] == "64990"
    assert derivative["funding_rate"] == "0.0001"


def test_perpetual_snapshot_fails_closed_when_ticker_becomes_stale() -> None:
    source = KrakenDerivativesMarketDataSource(
        FakeDerivativesRest(ticker_at=NOW - timedelta(seconds=11)),
        clock=FixedClock(),
        stale_after=timedelta(seconds=10),
    )

    with pytest.raises(StaleMarketDataError):
        asyncio.run(source.snapshot("BTC/USD"))


def test_perpetual_ticker_cannot_move_backwards_across_snapshots() -> None:
    rest = FakeDerivativesRest()
    source = KrakenDerivativesMarketDataSource(rest, clock=FixedClock())

    asyncio.run(source.snapshot("BTC/USD"))
    rest.ticker_at = TICKER_AT - timedelta(seconds=1)

    with pytest.raises(KrakenPayloadError, match="moved backwards"):
        asyncio.run(source.snapshot("BTC/USD"))


def test_parse_mark_candles_uses_candle_close_time_and_rejects_bad_chronology() -> None:
    candles: list[dict[str, object]] = [
        {"time": 1_795_000_000_000, "close": "65000"},
        {"time": 1_795_000_060_000, "close": "65010"},
    ]
    payload: dict[str, object] = {
        "candles": candles,
        "more_candles": False,
    }

    observations = parse_kraken_derivatives_mark_candles(payload, instrument=INSTRUMENT)

    assert observations[0].observed_at == datetime.fromtimestamp(
        1_795_000_000, tz=UTC
    ) + timedelta(minutes=1)
    assert observations[0].symbol == "BTC/USD"
    assert observations[1].last_price == Decimal("65010")

    reversed_payload: dict[str, object] = {
        "candles": [candles[1], candles[0]],
        "more_candles": False,
    }
    with pytest.raises(KrakenPayloadError, match="strictly chronological"):
        parse_kraken_derivatives_mark_candles(reversed_payload, instrument=INSTRUMENT)


def test_public_client_uses_public_charts_origin_without_private_authentication() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candles": [
                    {
                        "time": 1_795_000_000_000,
                        "open": "64990",
                        "high": "65010",
                        "low": "64980",
                        "close": "65000",
                        "volume": 10,
                    }
                ],
                "more_candles": False,
            },
        )

    async def run() -> tuple[MarketObservation, ...]:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenDerivativesPublicClient(
                "https://futures.kraken.test/derivatives/api/v3",
                client=http_client,
            )
            return await client.fetch_mark_history(
                INSTRUMENT,
                since=NOW - timedelta(minutes=32),
                until=NOW,
            )

    observations = asyncio.run(run())

    assert len(observations) == 1
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == "/api/charts/v1/mark/PF_XBTUSD/1m"
    assert request.url.params["from"] == str(int((NOW - timedelta(minutes=32)).timestamp()))
    assert request.url.params["to"] == str(int(NOW.timestamp()))
    assert "authorization" not in request.headers
    assert "api-key" not in request.headers
