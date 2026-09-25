from __future__ import annotations

from sqlalchemy import select

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket, PortfolioState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.persistence.campaign_runs import CampaignPaperRunLifecycle
from ai_spot_trader.persistence.models import PaperRunRecord
from ai_spot_trader.persistence.runs import (
    PaperRunRecoveryError,
    _legacy_projection,
    _normalize_universe,
    _portfolio_from_payload,
    _universe_from_record,
)


class DynamicCampaignPaperRunLifecycle(CampaignPaperRunLifecycle):
    """Canonical campaign recovery with Batch 19.4 dynamic held-market expansion.

    The immutable campaign keeps its bootstrap universe. On explicit resume only, markets for
    durable open positions are added to the new run's execution-universe payload before the base
    lifecycle validates the recovered portfolio. No separate ledger or recovery path is created.
    """

    def __init__(
        self,
        *args: object,
        settlement_asset: str,
        dynamic_market_types: tuple[MarketType, ...],
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._dynamic_bootstrap = self._execution_universe
        self._dynamic_settlement_asset = settlement_asset.strip().upper()
        self._dynamic_market_types = frozenset(dynamic_market_types)
        if not self._dynamic_settlement_asset:
            raise ValueError("dynamic recovery settlement_asset cannot be empty")
        if not self._dynamic_market_types or MarketType.FUTURE in self._dynamic_market_types:
            raise ValueError("dynamic recovery requires executable SPOT/PERPETUAL market types")

    async def initialize(self):  # type: ignore[no-untyped-def]
        if self._resume and self._current_run_id is None:
            await self._expand_universe_from_latest_durable_portfolio()
        return await super().initialize()

    async def _expand_universe_from_latest_durable_portfolio(self) -> None:
        async with self._sessions() as session:
            latest = await session.scalar(
                select(PaperRunRecord)
                .where(PaperRunRecord.campaign_id == self._campaign_id)
                .order_by(
                    PaperRunRecord.started_at.desc(),
                    PaperRunRecord.paper_run_id.desc(),
                )
                .limit(1)
            )
        if latest is None or latest.current_portfolio_payload is None:
            return
        recovered = _portfolio_from_payload(latest.current_portfolio_payload)
        held = _position_markets(
            recovered,
            settlement_asset=self._dynamic_settlement_asset,
            allowed_types=self._dynamic_market_types,
        )
        self._execution_universe = _normalize_universe(
            execution_universe=tuple(self._dynamic_bootstrap) + held,
            market_type=None,
            symbol=None,
        )
        self._market_type, self._symbol = _legacy_projection(self._execution_universe)

    def _validate_parent(self, parent: PaperRunRecord) -> None:
        if parent.campaign_id != self._campaign_id:
            raise PaperRunRecoveryError("PAPER recovery campaign mismatch")
        parent_universe = _universe_from_record(parent)
        if not set(self._dynamic_bootstrap).issubset(set(parent_universe)):
            raise PaperRunRecoveryError(
                "dynamic PAPER parent lost the immutable campaign bootstrap universe"
            )
        for market in parent_universe:
            _, quote = parse_canonical_symbol(market.symbol)
            if quote != self._dynamic_settlement_asset:
                raise PaperRunRecoveryError(
                    "dynamic PAPER parent contains a different settlement asset"
                )
            if market.market_type not in self._dynamic_market_types:
                raise PaperRunRecoveryError(
                    "dynamic PAPER parent contains a disabled market type"
                )


def _position_markets(
    portfolio: PortfolioState,
    *,
    settlement_asset: str,
    allowed_types: frozenset[MarketType],
) -> tuple[ExecutableMarket, ...]:
    markets: set[ExecutableMarket] = set()
    if MarketType.SPOT in allowed_types:
        for position in portfolio.positions:
            if position.quantity > 0:
                markets.add(
                    ExecutableMarket(
                        symbol=f"{position.asset}/{settlement_asset}",
                        market_type=MarketType.SPOT,
                    )
                )
    elif any(position.quantity > 0 for position in portfolio.positions):
        raise PaperRunRecoveryError("recovered SPOT inventory is disabled by dynamic campaign")

    if MarketType.PERPETUAL in allowed_types:
        for position in portfolio.derivative_positions:
            markets.add(
                ExecutableMarket(
                    symbol=position.symbol,
                    market_type=MarketType.PERPETUAL,
                )
            )
    elif portfolio.derivative_positions:
        raise PaperRunRecoveryError(
            "recovered derivative positions are disabled by dynamic campaign"
        )

    return tuple(sorted(markets, key=lambda item: (item.market_type.value, item.symbol)))
