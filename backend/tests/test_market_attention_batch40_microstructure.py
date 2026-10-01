from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityDataQuality,
    MarketActivitySnapshot,
    MarketActivityState,
    RadarInterestLevel,
    RadarStatus,
)
from ai_spot_trader.market.attention_microstructure import _enrich_snapshot
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureSnapshot,
    MicrostructureCharacteristic,
    MicrostructureDataQuality,
    MicrostructureStatus,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


def _activity(level: RadarInterestLevel = RadarInterestLevel.LOW) -> MarketActivitySnapshot:
    return MarketActivitySnapshot(
        market=MARKET,
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL,
        horizons=(),
        interest_level=level,
        interest_reasons=("OHLCV",) if level is not RadarInterestLevel.LOW else (),
        data_quality=ActivityDataQuality.COMPLETE,
    )


def _micro(*characteristics: MicrostructureCharacteristic) -> MarketMicrostructureSnapshot:
    return MarketMicrostructureSnapshot(
        market=MARKET,
        observed_at=NOW,
        status=MicrostructureStatus.AVAILABLE,
        data_quality=MicrostructureDataQuality.COMPLETE,
        quote_asset="USD",
        characteristics=characteristics,
    )


def test_microstructure_can_raise_attention_for_active_market_with_modest_ohlcv() -> None:
    item = _enrich_snapshot(
        _activity(),
        _micro(
            MicrostructureCharacteristic.TRADE_ACTIVITY_SURGE,
            MicrostructureCharacteristic.ORDER_BOOK_IMBALANCE,
        ),
    )
    assert item.interest_level is RadarInterestLevel.HIGH
    assert "TRADE_ACTIVITY_SURGE" in item.combined_characteristics
    assert "ORDER_BOOK_IMBALANCE" in item.combined_characteristics


def test_execution_cost_cautions_reduce_but_do_not_create_directional_signal() -> None:
    item = _enrich_snapshot(
        _activity(RadarInterestLevel.HIGH),
        _micro(
            MicrostructureCharacteristic.WIDE_SPREAD,
            MicrostructureCharacteristic.SLIPPAGE_RISK,
        ),
    )
    assert item.interest_level is RadarInterestLevel.MEDIUM
    assert any("coûteuse" in reason for reason in item.interest_reasons)


def test_informative_only_runtime_modules_do_not_import_agent_risk_broker_or_web() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "ai_spot_trader"
    targets = (
        root / "market" / "microstructure.py",
        root / "market" / "attention_microstructure.py",
        root / "integrations" / "kraken" / "microstructure.py",
    )
    forbidden = (
        "OpenAIWebAttentionResearcher",
        "PublicAttentionResearcher",
        "PublicResearchDecision",
        "web_search",
        "ai_spot_trader.agent",
        "ai_spot_trader.risk",
        "ai_spot_trader.broker",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in targets)
    for token in forbidden:
        assert token not in text


def test_microstructure_module_does_not_construct_or_send_orders() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "ai_spot_trader"
    text = (root / "market" / "microstructure.py").read_text(encoding="utf-8")
    assert "add_order" not in text.lower()
    assert "create_order" not in text.lower()
    assert "broker" not in text.lower()
