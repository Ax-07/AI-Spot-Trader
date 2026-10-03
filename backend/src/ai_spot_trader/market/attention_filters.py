from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from math import ceil
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
    LiquidityRegime,
    LiquidityRegimeCounts,
    MarketActivitySnapshot,
    MarketAttentionPolicy,
    MarketCatalogue,
    MarketTypeCounts,
    RadarInterestLevel,
    RadarStatus,
    SubthresholdActivitySnapshot,
    _liquidity_regime,
    _scan_allocations,
    _with_market_structure,
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


class Volume24hStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN_UNSUPPORTED_QUOTE = "UNKNOWN_UNSUPPORTED_QUOTE"
    UNKNOWN_UNSUPPORTED_MARKET_TYPE = "UNKNOWN_UNSUPPORTED_MARKET_TYPE"
    UNKNOWN_MISSING_QUOTE_VOLUME = "UNKNOWN_MISSING_QUOTE_VOLUME"
    UNKNOWN_INSUFFICIENT_HISTORY = "UNKNOWN_INSUFFICIENT_HISTORY"
    UNKNOWN_TECHNICAL_ERROR = "UNKNOWN_TECHNICAL_ERROR"


class Volume24hMeasurement(AttentionModel):
    status: Volume24hStatus
    value_usd: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_measurement(self) -> "Volume24hMeasurement":
        if self.status is Volume24hStatus.AVAILABLE:
            if self.value_usd is None:
                raise ValueError("available volume measurement requires value_usd")
        elif self.value_usd is not None:
            raise ValueError("unknown volume measurement cannot expose value_usd")
        return self


class Volume24hStatusCounts(AttentionModel):
    AVAILABLE: int = Field(default=0, ge=0)
    BELOW_THRESHOLD: int = Field(default=0, ge=0)
    UNKNOWN_UNSUPPORTED_QUOTE: int = Field(default=0, ge=0)
    UNKNOWN_UNSUPPORTED_MARKET_TYPE: int = Field(default=0, ge=0)
    UNKNOWN_MISSING_QUOTE_VOLUME: int = Field(default=0, ge=0)
    UNKNOWN_INSUFFICIENT_HISTORY: int = Field(default=0, ge=0)
    UNKNOWN_TECHNICAL_ERROR: int = Field(default=0, ge=0)


class MarketAttentionCoverageStatus(StrEnum):
    NO_MARKETS = "NO_MARKETS"
    COVERED = "COVERED"
    ROTATING = "ROTATING"
    TTL_EXPIRED = "TTL_EXPIRED"
    CONFIGURATION_TOO_SLOW = "CONFIGURATION_TOO_SLOW"


class MarketAttentionCoverageDiagnostics(AttentionModel):
    eligible_market_count: int = Field(default=0, ge=0)
    fresh_market_count: int = Field(default=0, ge=0)
    expired_market_count: int = Field(default=0, ge=0)
    unseen_market_count: int = Field(default=0, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    effective_scan_limit: int = Field(default=0, ge=0)
    estimated_refreshes_per_full_rotation: int = Field(default=0, ge=0)
    estimated_full_rotation_seconds: float = Field(default=0.0, ge=0)
    activity_ttl_seconds: float = Field(default=0.0, ge=0)
    oldest_activity_age_seconds: float | None = Field(default=None, ge=0)
    rotation_within_activity_ttl: bool = True
    status: MarketAttentionCoverageStatus = MarketAttentionCoverageStatus.NO_MARKETS

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "MarketAttentionCoverageDiagnostics":
        if (
            self.fresh_market_count
            + self.expired_market_count
            + self.unseen_market_count
            != self.eligible_market_count
        ):
            raise ValueError("coverage market counts must partition the eligible population")
        return self


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
    volume_24h_status_counts: Volume24hStatusCounts = Field(
        default_factory=Volume24hStatusCounts
    )
    coverage: MarketAttentionCoverageDiagnostics = Field(
        default_factory=MarketAttentionCoverageDiagnostics
    )
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
        volume_status_counts: Volume24hStatusCounts,
        coverage: MarketAttentionCoverageDiagnostics,
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
            volume_24h_status_counts=volume_status_counts,
            coverage=coverage,
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


def _volume_status_counts(
    measurements: tuple[Volume24hMeasurement, ...],
    *,
    minimum: Decimal | None,
) -> Volume24hStatusCounts:
    values = {
        "AVAILABLE": 0,
        "BELOW_THRESHOLD": 0,
        "UNKNOWN_UNSUPPORTED_QUOTE": 0,
        "UNKNOWN_UNSUPPORTED_MARKET_TYPE": 0,
        "UNKNOWN_MISSING_QUOTE_VOLUME": 0,
        "UNKNOWN_INSUFFICIENT_HISTORY": 0,
        "UNKNOWN_TECHNICAL_ERROR": 0,
    }
    for measurement in measurements:
        if measurement.status is Volume24hStatus.AVAILABLE:
            assert measurement.value_usd is not None
            if minimum is not None and measurement.value_usd < minimum:
                values["BELOW_THRESHOLD"] += 1
            else:
                values["AVAILABLE"] += 1
        else:
            values[measurement.status.value] += 1
    return Volume24hStatusCounts(**values)


def _classify_perpetual_liquidity(
    activities: tuple[MarketActivitySnapshot, ...],
    measurements: dict[ExecutableMarket, Volume24hMeasurement],
) -> tuple[MarketActivitySnapshot, ...]:
    references = {
        snapshot.market: measurement.value_usd
        for snapshot in activities
        if snapshot.market.market_type is MarketType.PERPETUAL
        and (measurement := measurements.get(snapshot.market)) is not None
        and measurement.status is Volume24hStatus.AVAILABLE
        and measurement.value_usd is not None
    }
    population = tuple(sorted(references.values()))

    classified: list[MarketActivitySnapshot] = []
    for snapshot in activities:
        if snapshot.market.market_type is not MarketType.PERPETUAL:
            classified.append(snapshot)
            continue
        reference = references.get(snapshot.market)
        with_liquidity = snapshot.model_copy(
            update={
                "liquidity_reference_usd": reference,
                "liquidity_regime": _liquidity_regime(reference, population),
            }
        )
        classified.append(_with_market_structure(with_liquidity))
    return tuple(classified)


def _coverage_diagnostics(
    *,
    eligible_markets: tuple[ExecutableMarket, ...],
    activity_cache: dict[ExecutableMarket, MarketActivitySnapshot],
    now: datetime,
    policy: MarketAttentionPolicy,
) -> MarketAttentionCoverageDiagnostics:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("coverage now must be timezone-aware")
    now = now.astimezone(UTC)
    ttl_seconds = float(policy.activity_ttl_seconds)

    fresh_count = 0
    expired_count = 0
    unseen_count = 0
    ages: list[float] = []
    for market in eligible_markets:
        snapshot = activity_cache.get(market)
        if snapshot is None:
            unseen_count += 1
            continue
        age = max(0.0, (now - snapshot.observed_at.astimezone(UTC)).total_seconds())
        ages.append(age)
        if age <= ttl_seconds:
            fresh_count += 1
        else:
            expired_count += 1

    populations = {
        market_type: sum(market.market_type is market_type for market in eligible_markets)
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL)
    }
    allocations = _scan_allocations(populations, limit=policy.scan_limit)
    refreshes_per_family = tuple(
        ceil(populations[market_type] / allocations[market_type])
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL)
        if populations[market_type] > 0 and allocations[market_type] > 0
    )
    refreshes = max(refreshes_per_family, default=0)
    estimated_seconds = float(refreshes) * float(policy.refresh_seconds)
    within_ttl = refreshes == 0 or estimated_seconds <= ttl_seconds
    eligible_count = len(eligible_markets)
    ratio = fresh_count / eligible_count if eligible_count else None

    if eligible_count == 0:
        status = MarketAttentionCoverageStatus.NO_MARKETS
    elif not within_ttl:
        status = MarketAttentionCoverageStatus.CONFIGURATION_TOO_SLOW
    elif expired_count > 0:
        status = MarketAttentionCoverageStatus.TTL_EXPIRED
    elif fresh_count == eligible_count:
        status = MarketAttentionCoverageStatus.COVERED
    else:
        status = MarketAttentionCoverageStatus.ROTATING

    return MarketAttentionCoverageDiagnostics(
        eligible_market_count=eligible_count,
        fresh_market_count=fresh_count,
        expired_market_count=expired_count,
        unseen_market_count=unseen_count,
        coverage_ratio=ratio,
        effective_scan_limit=sum(allocations.values()),
        estimated_refreshes_per_full_rotation=refreshes,
        estimated_full_rotation_seconds=estimated_seconds,
        activity_ttl_seconds=ttl_seconds,
        oldest_activity_age_seconds=max(ages) if ages else None,
        rotation_within_activity_ttl=within_ttl,
        status=status,
    )


class FilteredStructuredMarketAttentionRadar(StructuredMarketAttentionRadar):
    """Batch 44 Radar: v6 filters plus PERPETUAL liquidity and coverage diagnostics."""

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
        self._volume_24h_by_market: dict[ExecutableMarket, Volume24hMeasurement] = {}
        self._perpetual_volume_24h_usd: dict[ExecutableMarket, Decimal] = {}
        self._perpetual_volume_provider_configured = callable(
            getattr(catalogue, "volume_24h_usd_by_market", None)
        )
        self._perpetual_volume_refresh_failed = False
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
        return self._overview_v6(super().latest)

    def history(self, *, limit: int = 24) -> tuple[MarketAttentionOverviewV6, ...]:  # type: ignore[override]
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
                coverage=self._coverage(now),
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
        await self._refresh_perpetual_volume_24h(catalogue)
        return tuple(market for market in catalogue if self._market_cap_accepts(market))

    def _fresh_activities(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        activities = tuple(
            item for item in super()._fresh_activities(now) if self._market_cap_accepts(item.market)
        )
        self._volume_24h_by_market = {
            item.market: self._volume_24h_measurement(item.market, as_of=now)
            for item in activities
        }
        minimum = self.filters.min_volume_24h_usd
        if minimum is None:
            return activities
        return tuple(
            item
            for item in activities
            if (measurement := self._volume_24h_by_market.get(item.market)) is not None
            and measurement.status is Volume24hStatus.AVAILABLE
            and measurement.value_usd is not None
            and measurement.value_usd >= minimum
        )

    def _classify_liquidity(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[MarketActivitySnapshot, ...]:
        classified = super()._classify_liquidity(activities)
        return _classify_perpetual_liquidity(classified, self._volume_24h_by_market)

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
        return len(self._eligible_coverage_markets())

    def _eligible_coverage_markets(self) -> tuple[ExecutableMarket, ...]:
        return tuple(
            market
            for market in self._catalogue
            if self._scope_accepts_market(market) and self._market_cap_accepts(market)
        )

    def _coverage(self, now: datetime) -> MarketAttentionCoverageDiagnostics:
        return _coverage_diagnostics(
            eligible_markets=self._eligible_coverage_markets(),
            activity_cache=self._activity_cache,
            now=now,
            policy=self._policy,
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
        measurement = self._volume_24h_by_market.get(market)
        return bool(
            measurement is not None
            and measurement.status is Volume24hStatus.AVAILABLE
            and measurement.value_usd is not None
            and measurement.value_usd >= minimum
        )

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

    async def _refresh_perpetual_volume_24h(
        self,
        catalogue: tuple[ExecutableMarket, ...],
    ) -> None:
        relevant = tuple(
            market
            for market in catalogue
            if market.market_type is MarketType.PERPETUAL and self._scope_accepts_market(market)
        )
        if not relevant:
            self._perpetual_volume_24h_usd = {}
            self._perpetual_volume_refresh_failed = False
            return
        provider = getattr(self._catalogue_provider, "volume_24h_usd_by_market", None)
        if not callable(provider):
            self._perpetual_volume_24h_usd = {}
            self._perpetual_volume_refresh_failed = False
            return
        try:
            values = await provider()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._perpetual_volume_24h_usd = {}
            self._perpetual_volume_refresh_failed = True
            return
        self._perpetual_volume_refresh_failed = False
        relevant_set = set(relevant)
        self._perpetual_volume_24h_usd = {
            market: value
            for market, value in values.items()
            if market in relevant_set and value >= 0
        }

    def _volume_24h_measurement(
        self,
        market: ExecutableMarket,
        *,
        as_of: datetime,
    ) -> Volume24hMeasurement:
        _base, quote = parse_canonical_symbol(market.symbol)
        if quote.upper() != "USD":
            return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_UNSUPPORTED_QUOTE)

        if market.market_type is MarketType.PERPETUAL:
            if not self._perpetual_volume_provider_configured:
                return Volume24hMeasurement(
                    status=Volume24hStatus.UNKNOWN_UNSUPPORTED_MARKET_TYPE
                )
            if self._perpetual_volume_refresh_failed:
                return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_TECHNICAL_ERROR)
            value = self._perpetual_volume_24h_usd.get(market)
            if value is None:
                return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_MISSING_QUOTE_VOLUME)
            return Volume24hMeasurement(status=Volume24hStatus.AVAILABLE, value_usd=value)

        if market.market_type is not MarketType.SPOT:
            return Volume24hMeasurement(
                status=Volume24hStatus.UNKNOWN_UNSUPPORTED_MARKET_TYPE
            )
        cache = getattr(self._candles, "cache", None)
        if cache is None or not hasattr(cache, "history_as_of"):
            return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_TECHNICAL_ERROR)
        key = CandleKey(
            symbol=market.symbol,
            market_type=market.market_type,
            timeframe=CandleTimeframe.M5,
        )
        try:
            history = cache.history_as_of(key, as_of=as_of, limit=VOLUME_CANDLE_LIMIT)
        except Exception:
            return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_TECHNICAL_ERROR)
        value = _causal_spot_volume_24h_usd(history, as_of=as_of)
        if value is None:
            return Volume24hMeasurement(status=Volume24hStatus.UNKNOWN_INSUFFICIENT_HISTORY)
        return Volume24hMeasurement(status=Volume24hStatus.AVAILABLE, value_usd=value)

    def _volume_24h_usd(
        self,
        market: ExecutableMarket,
        *,
        as_of: datetime,
    ) -> Decimal | None:
        measurement = self._volume_24h_measurement(market, as_of=as_of)
        if measurement.status is not Volume24hStatus.AVAILABLE:
            return None
        return measurement.value_usd

    def _snapshot_v6(self, value: MarketAttentionSnapshotV5) -> MarketAttentionSnapshotV6:
        market = value.market_activity.market
        metadata = self._metadata_by_symbol.get(_market_base_asset(market))
        market_cap = metadata.market_cap_usd if metadata is not None else None
        volume = self._volume_24h_by_market.get(market)
        return MarketAttentionSnapshotV6(
            market_activity=value.market_activity,
            microstructure=value.microstructure,
            market_structure=value.market_structure,
            combined_characteristics=value.combined_characteristics,
            interest_level=value.interest_level,
            interest_reasons=value.interest_reasons,
            volume_24h_usd=(
                volume.value_usd
                if volume is not None and volume.status is Volume24hStatus.AVAILABLE
                else None
            ),
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
        volume_status_counts = _volume_status_counts(
            tuple(self._volume_24h_by_market.values()),
            minimum=filters.min_volume_24h_usd,
        )
        return MarketAttentionOverviewV6.from_v5(
            value,
            filters=filters,
            shortlist=shortlist,
            metadata_status=self._metadata_status,
            metadata_provider=self._metadata_provider_name,
            volume_status_counts=volume_status_counts,
            coverage=self._coverage(value.observed_at),
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

    window_end = final[-1].close_time.astimezone(UTC)
    window_start = window_end - VOLUME_WINDOW
    if final[0].open_time.astimezone(UTC) > window_start:
        return None
    in_window = tuple(
        candle
        for candle in final
        if candle.open_time.astimezone(UTC) >= window_start
        and candle.close_time.astimezone(UTC) <= window_end
    )
    if not in_window:
        return None
    return sum((item.volume * item.close for item in in_window), Decimal(0))
