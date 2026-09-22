from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.api.schemas import CycleDetailResponse, PaperRunResponse
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    AssetBalance,
    ExecutableMarket,
    MarketSelection,
    MarketSelectionInput,
    PortfolioState,
    market_selection_digest,
)
from ai_spot_trader.persistence.repository import _result_digest
from ai_spot_trader.persistence.runs import (
    PaperRunDefinition,
    PaperRunView,
    _legacy_projection,
    _normalize_universe,
)
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

NOW = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)
RUN = UUID("10000000-0000-0000-0000-000000000001")
CYCLE = UUID("20000000-0000-0000-0000-000000000002")
SELECTION = UUID("30000000-0000-0000-0000-000000000003")


def _selection(symbol: str, market_type: MarketType) -> MarketSelection:
    digest = market_selection_digest(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol=symbol,
        market_type=market_type,
        tool_traces=(),
        rationale="test",
    )
    return MarketSelection(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol=symbol,
        market_type=market_type,
        rationale="test",
        selection_digest=digest,
    )


def _selection_input() -> MarketSelectionInput:
    return MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=PortfolioState(
            portfolio_state_id=UUID(int=99),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        executable_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        aggressiveness=5,
    )


def _failed(selected: MarketSelection) -> TradingCycleResult:
    return TradingCycleResult(
        cycle_id=CYCLE,
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.MARKET,
            error_type="KrakenConnectionError",
        ),
        market_selection_input=_selection_input(),
        market_selection=selected,
    )


def test_cycle_digest_changes_when_typed_market_selection_changes() -> None:
    spot = _failed(_selection("BTC/USD", MarketType.SPOT))
    perp = _failed(_selection("ETH/USD", MarketType.PERPETUAL))
    assert _result_digest(spot, paper_run_id=RUN) != _result_digest(
        perp,
        paper_run_id=RUN,
    )


def test_legacy_paper_run_definition_and_view_positional_contract_remains_valid() -> None:
    definition = PaperRunDefinition(RUN, NOW, "SPOT", "BTC/USD")
    view = PaperRunView(RUN, NOW, None, "SPOT", "BTC/USD")
    assert definition.market_type == "SPOT" and definition.symbol == "BTC/USD"
    assert view.execution_universe == ()


def test_singleton_run_projects_legacy_fields_but_multi_market_run_does_not() -> None:
    singleton = _normalize_universe(
        execution_universe=None,
        market_type="SPOT",
        symbol="BTC/USD",
    )
    assert _legacy_projection(singleton) == ("SPOT", "BTC/USD")

    multi = (
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
    )
    assert _legacy_projection(multi) == (None, None)


def test_api_run_contract_represents_multi_market_without_fake_multi_symbol() -> None:
    response = PaperRunResponse(
        paper_run_id=RUN,
        started_at=NOW,
        market_type=None,
        symbol=None,
        execution_universe=(
            {"symbol": "ETH/USD", "market_type": "PERPETUAL"},
            {"symbol": "BTC/USD", "market_type": "SPOT"},
        ),
    )
    assert response.market_type is None
    assert response.symbol is None
    assert tuple(item.symbol for item in response.execution_universe) == (
        "ETH/USD",
        "BTC/USD",
    )


def test_cycle_detail_api_can_expose_selection_before_final_agent_input() -> None:
    selection = _selection("ETH/USD", MarketType.PERPETUAL)
    response = CycleDetailResponse(
        cycle_id=CYCLE,
        status="FAILED",
        recorded_at=NOW,
        market_selection_input=_selection_input().model_dump(mode="json"),
        market_selection=selection.model_dump(mode="json"),
        agent_input=None,
    )
    assert response.market_selection is not None
    assert response.market_selection["symbol"] == "ETH/USD"
    assert response.agent_input is None


def test_market_selection_input_refuses_nondeterministic_universe_order() -> None:
    with pytest.raises(ValueError, match="sorted order"):
        MarketSelectionInput(
            cycle_id=CYCLE,
            created_at=NOW,
            portfolio_state=PortfolioState(
                portfolio_state_id=UUID(int=98),
                as_of=NOW,
                balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
            ),
            executable_markets=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
                ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
            ),
            aggressiveness=5,
        )


def test_executable_market_refuses_dated_future() -> None:
    with pytest.raises(ValueError, match="FUTURE"):
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.FUTURE)


def test_selection_input_refuses_portfolio_snapshot_from_the_future() -> None:
    with pytest.raises(ValueError, match="newer"):
        MarketSelectionInput(
            cycle_id=CYCLE,
            created_at=NOW,
            portfolio_state=PortfolioState(
                portfolio_state_id=UUID(int=97),
                as_of=NOW.replace(microsecond=1),
                balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
            ),
            executable_markets=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
            ),
            aggressiveness=5,
        )


def test_market_selection_refuses_tool_trace_completed_after_selection() -> None:
    from datetime import timedelta

    from ai_spot_trader.domain.models import AgentToolTrace, canonical_json_digest

    result = {"ok": True}
    trace = AgentToolTrace(
        call_id="late",
        tool_name="get_market_snapshot",
        arguments={"symbol": "BTC/USD", "market_type": "SPOT"},
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        status="SUCCESS",
        result=result,
        result_digest=canonical_json_digest(result),
    )
    digest = market_selection_digest(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        tool_traces=(trace,),
    )
    with pytest.raises(ValueError, match="after selected_at"):
        MarketSelection(
            selection_id=SELECTION,
            cycle_id=CYCLE,
            selected_at=NOW,
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            tool_traces=(trace,),
            selection_digest=digest,
        )


def test_paper_run_definition_refuses_mixed_legacy_and_multi_market_metadata() -> None:
    with pytest.raises(ValueError, match="either execution_universe or legacy"):
        PaperRunDefinition(
            RUN,
            NOW,
            "SPOT",
            "BTC/USD",
            (ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
        )


def test_run_normalization_refuses_mixed_legacy_and_execution_universe_arguments() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        _normalize_universe(
            execution_universe=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
            ),
            market_type="SPOT",
            symbol="BTC/USD",
        )


def test_cycle_summary_exposes_typed_selection_before_decision_exists() -> None:
    from ai_spot_trader.persistence.models import CycleRecord
    from ai_spot_trader.persistence.query import _cycle_summary

    record = CycleRecord(
        cycle_id=CYCLE,
        paper_run_id=RUN,
        status="FAILED",
        recorded_at=NOW,
        result_digest="a" * 64,
        failure_stage="MARKET",
        failure_error_type="KrakenConnectionError",
        failure_timed_out=False,
        market_selection_payload={
            "symbol": "ETH/USD",
            "market_type": "PERPETUAL",
        },
        agent_tool_traces_payload=[],
    )
    summary = _cycle_summary(record)
    assert summary.symbol == "ETH/USD"
    assert summary.market_type == "PERPETUAL"
    assert summary.decision_action is None


def test_repository_graph_serializes_selection_before_any_final_decision() -> None:
    from ai_spot_trader.persistence.models import CycleRecord
    from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository

    class CollectingSession:
        def __init__(self) -> None:
            self.items: list[object] = []

        def add(self, value: object) -> None:
            self.items.append(value)

    result = _failed(_selection("ETH/USD", MarketType.PERPETUAL))
    session = CollectingSession()
    repository = object.__new__(SqlAlchemyCycleAuditRepository)
    repository._add_graph(  # type: ignore[arg-type]
        session,
        result=result,
        digest=_result_digest(result, paper_run_id=RUN),
        paper_run_id=RUN,
    )
    cycle = next(item for item in session.items if isinstance(item, CycleRecord))
    assert cycle.market_selection_input_payload is not None
    assert cycle.market_selection_payload is not None
    assert cycle.market_selection_payload["symbol"] == "ETH/USD"
    assert cycle.market_selection_payload["market_type"] == "PERPETUAL"
    assert cycle.agent_input_payload is None


def test_multi_market_run_record_round_trips_without_legacy_multi_placeholder() -> None:
    from ai_spot_trader.persistence.models import PaperRunRecord
    from ai_spot_trader.persistence.runs import _view

    record = PaperRunRecord(
        paper_run_id=RUN,
        started_at=NOW,
        ended_at=None,
        market_type=None,
        symbol=None,
        execution_universe_payload=[
            {"symbol": "ETH/USD", "market_type": "PERPETUAL"},
            {"symbol": "BTC/USD", "market_type": "SPOT"},
        ],
    )
    view = _view(record)
    assert view.market_type is None
    assert view.symbol is None
    assert view.execution_universe == (
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
    )
