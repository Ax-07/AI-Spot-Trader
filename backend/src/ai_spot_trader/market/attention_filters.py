from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.market.attention import (
    ActivityDataQualityCounts,
    ActivityErrorCounts,
    ActivityMarketTypeStatusCounts,
    ActivityPayloadStageCounts,
    ActivityStateCounts,
    ActivityStatusCounts,
    AttentionModel,
    LiquidityRegimeCounts,
    MarketActivitySnapshot,
    MarketAttentionPolicy,
    MarketCatalogue,
    MarketTypeCounts,
    RadarInterestLevel,
    RadarStatus,
    SubthresholdActivitySnapshot,
)
from ai_spot_trader.market.attention_microstructure import (
    MicrostructureQualityCounts,
    MicrostructureStatusCounts,
)
from ai_spot_trader.market.attention_scope_trend import MarketActivitySnapshotV4, MarketScope
from ai_spot_trader.market.attention_structure import (
    MarketAttentionOverviewV5,
    MarketAttentionSnapshotV5,
    StructuredMarketAttentionRadar,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleStreamService, CandleTimeframe
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureSnapshot,
    MicrostructurePolicy,
    MicrostructureProvider,
)
from ai_spot_trader.market.structure import MarketStructurePolicy, MultiTimeframeMarketStructure

MARKET_CAP_MICRO_MAX_USD = Decimal("100000000")
MARKET_CAP_SMALL_MAX_USD = Decimal("1000000000")
MARKET_CAP_MID_MAX_USD = Decimal("10000000000")
VOLUME_WINDOW = timedelta(hours=24)
VOLUME_CANDLE_LIMIT = 720


class MarketCapCategory(StrEnum):
    UNKNOWN = "UNKNOWN"
    MICRO = "MICRO"
    SMALL = "SMALL"
    MID = "MID"
    LARGE = "LARGE"


class MarketMetadataSnapshot(AttentionModel):
    asset_symbol: str
    circulating_supply: Decimal | None = Field(default=None, ge=0)
    market_cap_usd: Decimal | None = Field(default=None, ge=0)
    market_cap_rank: int | None = Field(default=None, ge=1)
    observed_at: datetime
    provider: str

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketMetadataSnapshot":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market metadata observed_at must be timezone-aware")
        if not self.asset_symbol.strip():
            raise ValueError("market metadata asset_symbol cannot be blank")
        if not self.provider.strip():
            raise ValueError("market metadata provider cannot be blank")
        return self


class MarketMetadataProvider(Protocol):
    async def metadata_by_symbol(self) -> dict[str, MarketMetadataSnapshot]: ...

    async def aclose(self) -> None: ...


class MarketAttentionFilters(AttentionModel):
    market_scope: MarketScope = MarketScope.ALL
    min_volume_24h_usd: Decimal | None = Field(default=None, ge=0)
    market_cap_categories: tuple[MarketCapCategory, ...] = ()
    min_market_cap_usd: Decimal | None = Field(default=None, ge=0)
    max_market_cap_usd: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_filters(self) -> "MarketAttentionFilters":
        if (
            self.min_market_cap_usd is not None
            and self.max_market_cap_usd is not None
            and self.min_market_cap_usd > self.max_market_cap_usd
        ):
            raise ValueError("min_market_cap_usd cannot exceed max_market_cap_usd")
        if MarketCapCategory.UNKNOWN in self.market_cap_categories:
            raise ValueError("UNKNOWN cannot be selected as a market cap filter category")
        if len(set(self.market_cap_categories)) != len(self.market_cap_categories):
            raise ValueError("market_cap_categories cannot contain duplicates")
        return self

    @property
    def market_cap_filter_enabled(self) -> bool:
        return bool(
            self.market_cap_categories
            or self.min_market_cap_usd is not None
            or self.max_market_cap_usd is not None
        )


class MarketAttentionSnapshotV6(AttentionModel):
    market_activity: MarketActivitySnapshotV4
    microstructure: MarketMicrostructureSnapshot
    market_structure: MultiTimeframeMarketStructure
    combined_characteristics: tuple[str, ...] = ()
    interest_level: RadarInterestLevel = RadarInterestLevel.LOW
    interest_reasons: tuple[str, ...] = ()
    volume_24h_usd: Decimal | None = Field(default=None, ge=0)
    market_cap_usd: Decimal | None = Field(default=None, ge=0)
    market_cap_category: MarketCapCategory = MarketCapCategory.UNKNOWN
    market_cap_rank: int | None = Field(default=None, ge=1)
    circulating_supply: Decimal | None = Field(default=None, ge=0)
    market_cap_provider: str | None = None
    market_cap_observed_at: datetime | None = None

    @property
    def market(self) -> ExecutableMarket:
        return self.market_activity.market

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketAttentionSnapshotV6":
        if self.market_cap_observed_at is not None:
            if (
                self.market_cap_observed_at.tzinfo is None
                or self.market_cap_observed_at.utcoffset() is None
            ):
                raise ValueError("market cap observed_at must be timezone-aware")
        return self


class MarketAttentionOverviewV6(AttentionModel):
    protocol_version: str = "market-attention-radar-v6"
    observed_at: datetime
    status: RadarStatus
    informative_only: bool = True
    market_scope: MarketScope = MarketScope.ALL
    filters: MarketAttentionFilters = Field(default_factory=MarketAttentionFilters)
    catalogue_market_count: int = Field(default=0, ge=0)
    cached_activity_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    scanned_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    fresh_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    candidate_market_count: int = Field(default=0, ge=0)
    activity_status_counts: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    activity_state_counts: ActivityStateCounts = Field(default_factory=ActivityStateCounts)
    activity_data_quality_counts: ActivityDataQualityCounts = Field(
        default_factory=ActivityDataQualityCounts
    )
    activity_error_counts: ActivityErrorCounts = Field(default_factory=ActivityErrorCounts)
    activity_payload_stage_counts: ActivityPayloadStageCounts = Field(
        default_factory=ActivityPayloadStageCounts
    )
    activity_market_type_status_counts: ActivityMarketTypeStatusCounts = Field(
        default_factory=ActivityMarketTypeStatusCounts
    )
    liquidity_regime_counts: LiquidityRegimeCounts = Field(default_factory=LiquidityRegimeCounts)
    microstructure_scanned_market_count: int = Field(default=0, ge=0)
    microstructure_cached_market_count: int = Field(default=0, ge=0)
    microstructure_status_counts: MicrostructureStatusCounts = Field(
        default_factory=MicrostructureStatusCounts
    )
    microstructure_quality_counts: MicrostructureQualityCounts = Field(
        default_factory=MicrostructureQualityCounts
    )
    microstructure_error_counts: dict[str, int] = Field(default_factory=dict)
    market_cap_metadata_status: RadarStatus = RadarStatus.PARTIAL
    market_cap_metadata_provider: str | None = None
    subthreshold_activity: tuple[SubthresholdActivitySnapshot, ...] = ()
    shortlist: tuple[MarketAttentionSnapshotV6, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_overview(self) -> "MarketAttentionOverviewV6":
        if self.protocol_version != "market-attention-radar-v6":
            raise ValueError("unsupported market attention protocol")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market attention observed_at must be timezone-aware")
        if not self.informative_only:
            raise ValueError("Market Attention Radar v6 must remain informative_only")
        if self.filters.market_scope is not self.market_scope:
            raise ValueError("market attention filters and market_scope must match")
        return self

    @classmethod
    def from_v5(
        cls,
        value: MarketAttentionOverviewV5,
        *,
        filters: MarketAttentionFilters,
        shortlist: tuple[MarketAttentionSnapshotV6, ...],
        metadata_status: RadarStatus,
        metadata_provider: str | None,
    ) -> "MarketAttentionOverviewV6":
        payload = value.model_dump(
            exclude={"protocol_version", "shortlist", "candidate_market_count"}
        )
        return cls(
            **payload,
            filters=filters,
            candidate_market_count=len(shortlist),
            shortlist=shortlist,
            market_cap_metadata_status=metadata_status,
            market_cap_metadata_provider=metadata_provider,
        )


def market_cap_category(value: Decimal | None) -> MarketCapCategory:
    if value is None or value < 0:
        return MarketCapCategory.UNKNOWN
    if value < MARKET_CAP_MICRO_MAX_USD:
        return MarketCapCategory.MICRO
    if value < MARKET_CAP_SMALL_MAX_USD:
        return MarketCapCategory.SMALL
    if value < MARKET_CAP_MID_MAX_USD:
        return MarketCapCategory.MID
    return MarketCapCategory.LARGE


def _market_base_asset(market: ExecutableMarket) -> str:
    base, _quote = parse_canonical_symbol(market.symbol)
    return base.upper()


def _metadata_accepts(
    metadata: MarketMetadataSnapshot | None,
    filters: MarketAttentionFilters,
) -> bool:
    if not filters.market_cap_filter_enabled:
        return True
    if metadata is None or metadata.market_cap_usd is None:
        return False
    value = metadata.market_cap_usd
    if filters.min_market_cap_usd is not None and value < filters.min_market_cap_usd:
        return False
    if filters.max_market_cap_usd is not None and value > filters.max_market_cap_usd:
        return False
    if filters.market_cap_categories:
        return market_cap_category(value) in filters.market_cap_categories
    return True


class FilteredStructuredMarketAttentionRadar(StructuredMarketAttentionRadar):
    """Batch 43 Radar: runtime volume/market-cap filters around the canonical v5 pipeline."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        microstructure_provider: MicrostructureProvider,
        metadata_provider: MarketMetadataProvider,
        policy: MarketAttentionPolicy | None = None,
        microstructure_policy: MicrostructurePolicy | None = None,
        structure_policy: MarketStructurePolicy | None = None,
    ) -> None:
        super().__init__(
            candle_service=candle_service,
            catalogue=catalogue,
            microstructure_provider=microstructure_provider,
            policy=policy,
            microstructure_policy=microstructure_policy,
            structure_policy=structure_policy,
        )
        self._metadata_provider = metadata_provider
        self._filters = MarketAttentionFilters()
        self._metadata_by_symbol: dict[str, MarketMetadataSnapshot] = {}
        self._metadata_status = RadarStatus.PARTIAL
        self._metadata_provider_name: str | None = None
        self._volume_24h_by_market: dict[ExecutableMarket, Decimal | None] = {}
        self._v6_latest: MarketAttentionOverviewV6 | None = None
        self._v6_history: deque[MarketAttentionOverviewV6] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def filters(self) -> MarketAttentionFilters:
        if self._filters.market_scope is self._market_scope:
            return self._filters
        return self._filters.model_copy(update={"market_scope": self._market_scope})

    @property
    def latest(self) -> MarketAttentionOverviewV6:  # type: ignore[override]
        if self._v6_latest is not None:
            return self._v6_latest
        base = super().latest
        return self._overview_v6(base)

    def history(  # type: ignore[override]
        self, *, limit: int = 24
    ) -> tuple[MarketAttentionOverviewV6, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._v6_history)[-limit:]

    async def set_market_scope(
        self,
        market_scope: MarketScope,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6:
        if not isinstance(market_scope, MarketScope):
            market_scope = MarketScope(market_scope)
        return await self.set_filters(
            self.filters.model_copy(update={"market_scope": market_scope}),
            observed_at=observed_at,
        )

    async def set_filters(
        self,
        filters: MarketAttentionFilters,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6:
        if not isinstance(filters, MarketAttentionFilters):
            filters = MarketAttentionFilters.model_validate(filters)
        if self._closed:
            raise RuntimeError("market attention radar is closed")

        async with self._scope_refresh_lock:
            self._market_scope = filters.market_scope
            self._filters = filters
            now = (observed_at or datetime.now(UTC)).astimezone(UTC)
            self._v6_latest = MarketAttentionOverviewV6(
                observed_at=now,
                status=RadarStatus.PARTIAL,
                informative_only=True,
                market_scope=filters.market_scope,
                filters=filters,
                catalogue_market_count=self._scope_catalogue_count(),
                market_cap_metadata_status=self._metadata_status,
                market_cap_metadata_provider=self._metadata_provider_name,
            )
            return await self._refresh_v4_once(observed_at=observed_at)

    async def _refresh_v4_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6:
        base = await super()._refresh_v4_once(observed_at=observed_at)
        overview = self._overview_v6(base)
        self._v6_latest = overview
        self._v6_history.append(overview)
        return overview

    async def _catalogue_if_due(self, now: datetime) -> tuple[ExecutableMarket, ...]:
        catalogue = await super()._catalogue_if_due(now)
        await self._refresh_market_metadata()
        return tuple(market for market in catalogue if self._market_cap_accepts(market))

    def _fresh_activities(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        activities = tuple(
            item for item in super()._fresh_activities(now) if self._market_cap_accepts(item.market)
        )
        for item in activities:
            self._volume_24h_by_market[item.market] = self._volume_24h_usd(
                item.market,
                as_of=now,
            )
        minimum = self.filters.min_volume_24h_usd
        if minimum is None:
            return activities
        return tuple(
            item
            for item in activities
            if (value := self._volume_24h_by_market.get(item.market)) is not None
            and value >= minimum
        )

    def _next_micro_batch(
        self,
        markets: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        eligible = tuple(
            market
            for market in markets
            if self._market_cap_accepts(market) and self._volume_filter_accepts(market)
        )
        return super()._next_micro_batch(eligible)

    def _fresh_microstructure(
        self,
        now: datetime,
    ) -> dict[ExecutableMarket, MarketMicrostructureSnapshot]:
        values = super()._fresh_microstructure(now)
        return {
            market: snapshot
            for market, snapshot in values.items()
            if self._market_cap_accepts(market) and self._volume_filter_accepts(market)
        }

    def _scope_catalogue_count(self) -> int:
        return sum(
            self._scope_accepts_market(market) and self._market_cap_accepts(market)
            for market in self._catalogue
        )

    async def aclose(self) -> None:
        try:
            await self._metadata_provider.aclose()
        finally:
            await super().aclose()

    def _scope_accepts_market(self, market: ExecutableMarket) -> bool:
        if self._market_scope is MarketScope.ALL:
            return market.market_type in (MarketType.SPOT, MarketType.PERPETUAL)
        if self._market_scope is MarketScope.SPOT:
            return market.market_type is MarketType.SPOT
        return market.market_type is MarketType.PERPETUAL

    def _market_cap_accepts(self, market: ExecutableMarket) -> bool:
        metadata = self._metadata_by_symbol.get(_market_base_asset(market))
        return _metadata_accepts(metadata, self.filters)

    def _volume_filter_accepts(self, market: ExecutableMarket) -> bool:
        minimum = self.filters.min_volume_24h_usd
        if minimum is None:
            return True
        value = self._volume_24h_by_market.get(market)
        return value is not None and value >= minimum

    async def _refresh_market_metadata(self) -> None:
        try:
            values = await self._metadata_provider.metadata_by_symbol()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._metadata_status = (
                RadarStatus.PARTIAL if self._metadata_by_symbol else RadarStatus.ERROR
            )
            return
        if not values:
            self._metadata_status = (
                RadarStatus.PARTIAL if self._metadata_by_symbol else RadarStatus.ERROR
            )
            return
        normalized = {key.strip().upper(): value for key, value in values.items() if key.strip()}
        self._metadata_by_symbol = normalized
        providers = sorted({item.provider for item in normalized.values() if item.provider})
        self._metadata_provider_name = providers[0] if len(providers) == 1 else "MULTIPLE"
        self._metadata_status = RadarStatus.AVAILABLE

    def _volume_24h_usd(
        self,
        market: ExecutableMarket,
        *,
        as_of: datetime,
    ) -> Decimal | None:
        if market.market_type is not MarketType.SPOT:
            return None
        _base, quote = parse_canonical_symbol(market.symbol)
        if quote.upper() != "USD":
            return None
        cache = getattr(self._candles, "cache", None)
        if cache is None or not hasattr(cache, "history_as_of"):
            return None
        key = CandleKey(
            symbol=market.symbol,
            market_type=market.market_type,
            timeframe=CandleTimeframe.M5,
        )
        try:
            history = cache.history_as_of(key, as_of=as_of, limit=VOLUME_CANDLE_LIMIT)
        except Exception:
            return None
        return _causal_spot_volume_24h_usd(history, as_of=as_of)

    def _snapshot_v6(self, value: MarketAttentionSnapshotV5) -> MarketAttentionSnapshotV6:
        market = value.market_activity.market
        metadata = self._metadata_by_symbol.get(_market_base_asset(market))
        market_cap = metadata.market_cap_usd if metadata is not None else None
        return MarketAttentionSnapshotV6(
            market_activity=value.market_activity,
            microstructure=value.microstructure,
            market_structure=value.market_structure,
            combined_characteristics=value.combined_characteristics,
            interest_level=value.interest_level,
            interest_reasons=value.interest_reasons,
            volume_24h_usd=self._volume_24h_by_market.get(market),
            market_cap_usd=market_cap,
            market_cap_category=market_cap_category(market_cap),
            market_cap_rank=(metadata.market_cap_rank if metadata is not None else None),
            circulating_supply=(metadata.circulating_supply if metadata is not None else None),
            market_cap_provider=(metadata.provider if metadata is not None else None),
            market_cap_observed_at=(metadata.observed_at if metadata is not None else None),
        )

    def _overview_v6(self, value: MarketAttentionOverviewV5) -> MarketAttentionOverviewV6:
        filters = self.filters
        shortlist = tuple(self._snapshot_v6(item) for item in value.shortlist)
        return MarketAttentionOverviewV6.from_v5(
            value,
            filters=filters,
            shortlist=shortlist,
            metadata_status=self._metadata_status,
            metadata_provider=self._metadata_provider_name,
        )


def _causal_spot_volume_24h_usd(
    candles: tuple[Candle, ...],
    *,
    as_of: datetime,
) -> Decimal | None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("volume as_of must be timezone-aware")
    as_of = as_of.astimezone(UTC)
    final = tuple(
        candle
        for candle in candles
        if candle.is_final
        and candle.timeframe is CandleTimeframe.M5
        and candle.close_time.astimezone(UTC) <= as_of
    )
    if not final:
        return None
    final = tuple(sorted(final, key=lambda item: item.open_time))
    window_start = as_of - VOLUME_WINDOW
    if final[0].open_time.astimezone(UTC) > window_start:
        return None
    in_window = tuple(
        candle
        for candle in final
        if candle.open_time.astimezone(UTC) >= window_start
        and candle.close_time.astimezone(UTC) <= as_of
    )
    return sum((item.volume * item.close for item in in_window), Decimal(0))
