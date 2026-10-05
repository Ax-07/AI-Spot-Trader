from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    AggressivenessContext,
    ExecutionCostContext,
    ExecutableMarket,
    PortfolioState,
    TradingStyleContext,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.market.attention import RadarStatus
from ai_spot_trader.market.research import (
    MarketResearchMarket,
    MarketResearchService,
    MarketResearchSnapshot,
)

MARKET_DISCOVERY_PROTOCOL_VERSION = "market-discovery-v1"
DEFAULT_RADAR_STALE_AFTER_SECONDS = 900.0

DiscoveryStatus = Literal[
    "REFRESHED",
    "CACHE_REUSED",
    "FALLBACK",
    "SKIPPED_MANAGEMENT",
]
DiscoverySource = Literal["LEGACY_AGENT", "RADAR_SHORTLIST"]


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarketDiscoveryPolicy(DiscoveryModel):
    """Deterministic bounds around dynamic Kraken market discovery."""

    protocol_version: str = MARKET_DISCOVERY_PROTOCOL_VERSION
    market_types: tuple[MarketType, ...]
    catalog_refresh_seconds: int = Field(default=900, ge=60, le=86_400)
    watchlist_refresh_seconds: int = Field(default=900, ge=60, le=86_400)
    refresh_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    candidate_probe_limit: int = Field(default=24, ge=1, le=200)
    candidate_limit: int = Field(default=12, ge=1, le=100)
    watchlist_limit: int = Field(default=6, ge=1, le=20)
    max_snapshot_age_seconds: int = Field(default=120, ge=1, le=3_600)
    min_window_observations: int = Field(default=2, ge=0, le=10_000)
    require_complete_window: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> "MarketDiscoveryPolicy":
        if self.protocol_version != MARKET_DISCOVERY_PROTOCOL_VERSION:
            raise ValueError("unsupported market discovery protocol")
        if not self.market_types:
            raise ValueError("market discovery requires at least one market type")
        if MarketType.FUTURE in self.market_types:
            raise ValueError("dated FUTURE markets are not discoverable for execution")
        ordered = tuple(sorted(set(self.market_types), key=lambda value: value.value))
        if ordered != self.market_types:
            raise ValueError("market discovery market_types must be unique and sorted")
        if self.candidate_limit > self.candidate_probe_limit:
            raise ValueError("candidate_limit cannot exceed candidate_probe_limit")
        if self.watchlist_limit > self.candidate_limit:
            raise ValueError("watchlist_limit cannot exceed candidate_limit")
        return self


class MarketCandidate(DiscoveryModel):
    market: ExecutableMarket
    status: str | None = None
    venue_symbol: str
    snapshot: MarketResearchSnapshot

    @model_validator(mode="after")
    def validate_candidate(self) -> "MarketCandidate":
        if self.snapshot.symbol != self.market.symbol:
            raise ValueError("candidate snapshot symbol mismatch")
        if self.snapshot.market_type is not self.market.market_type:
            raise ValueError("candidate snapshot market_type mismatch")
        return self


class MarketDiscoveryInput(DiscoveryModel):
    discovery_id: UUID
    created_at: datetime
    portfolio_state: PortfolioState
    candidates: tuple[MarketCandidate, ...]
    previous_watchlist: tuple[ExecutableMarket, ...] = ()
    watchlist_limit: int = Field(ge=1, le=20)
    aggressiveness: int = Field(ge=1, le=10)
    aggressiveness_context: AggressivenessContext
    trading_style_context: TradingStyleContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    execution_cost_context: ExecutionCostContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    market_discovery_context: dict[str, object]

    @model_validator(mode="after")
    def validate_input(self) -> "MarketDiscoveryInput":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("market discovery created_at must be timezone-aware")
        if self.portfolio_state.as_of > self.created_at:
            raise ValueError("PortfolioState cannot be newer than MarketDiscoveryInput")
        if not self.candidates:
            raise ValueError("market discovery requires candidates")
        if len(self.candidates) > 100:
            raise ValueError("market discovery candidates exceed hard bound")
        ordered = tuple(
            sorted(
                self.candidates,
                key=lambda item: (item.market.market_type.value, item.market.symbol),
            )
        )
        if ordered != self.candidates:
            raise ValueError("market discovery candidates must use deterministic order")
        candidate_markets = tuple(item.market for item in self.candidates)
        if len(set(candidate_markets)) != len(candidate_markets):
            raise ValueError("market discovery candidates must be unique")
        if any(item.snapshot.as_of > self.created_at for item in self.candidates):
            raise ValueError("market discovery cannot contain future snapshots")
        previous = tuple(
            sorted(
                set(self.previous_watchlist),
                key=lambda item: (item.market_type.value, item.symbol),
            )
        )
        if previous != self.previous_watchlist:
            raise ValueError("previous_watchlist must be unique and sorted")
        if self.aggressiveness_context.level != self.aggressiveness:
            raise ValueError("aggressiveness_context level mismatch")
        if (self.trading_style_context is None) != (self.execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        return self


class WatchlistEntry(DiscoveryModel):
    market: ExecutableMarket
    rationale: str = Field(min_length=1)


class WatchlistSelection(DiscoveryModel):
    discovery_id: UUID
    selected_at: datetime
    entries: tuple[WatchlistEntry, ...]
    rationale: str = Field(min_length=1)

    @property
    def markets(self) -> tuple[ExecutableMarket, ...]:
        return tuple(entry.market for entry in self.entries)

    @model_validator(mode="after")
    def validate_selection(self) -> "WatchlistSelection":
        if self.selected_at.tzinfo is None or self.selected_at.utcoffset() is None:
            raise ValueError("watchlist selected_at must be timezone-aware")
        if not self.entries:
            raise ValueError("watchlist cannot be empty")
        markets = self.markets
        ordered = tuple(sorted(markets, key=lambda item: (item.market_type.value, item.symbol)))
        if ordered != markets:
            raise ValueError("watchlist entries must use deterministic order")
        if len(set(markets)) != len(markets):
            raise ValueError("watchlist markets must be unique")
        return self


class MarketDiscoveryAudit(DiscoveryModel):
    protocol_version: str = MARKET_DISCOVERY_PROTOCOL_VERSION
    source: DiscoverySource = "LEGACY_AGENT"
    discovery_id: UUID | None = None
    status: DiscoveryStatus
    observed_at: datetime
    trading_style_context: TradingStyleContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    execution_cost_context: ExecutionCostContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    catalogue_refreshed: bool = False
    catalogue_market_count: int = 0
    compatible_market_count: int = 0
    probed_market_count: int = 0
    candidate_market_count: int = 0
    input_created_at: datetime | None = None
    candidates: tuple[MarketCandidate, ...] = ()
    selection_selected_at: datetime | None = None
    previous_watchlist: tuple[ExecutableMarket, ...] = ()
    effective_watchlist: tuple[ExecutableMarket, ...] = ()
    added_markets: tuple[ExecutableMarket, ...] = ()
    maintained_markets: tuple[ExecutableMarket, ...] = ()
    removed_markets: tuple[ExecutableMarket, ...] = ()
    selection_rationale: str | None = None
    selection_entries: tuple[WatchlistEntry, ...] = ()
    radar_observed_at: datetime | None = None
    radar_status: RadarStatus | None = None
    radar_shortlist_market_count: int = Field(default=0, ge=0)
    radar_shortlist: tuple[ExecutableMarket, ...] = ()
    radar_rejected_markets: tuple[ExecutableMarket, ...] = ()
    error_type: str | None = None
    next_refresh_at: datetime | None = None

    @model_validator(mode="after")
    def validate_audit(self) -> "MarketDiscoveryAudit":
        if (self.trading_style_context is None) != (self.execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        for value in (
            self.observed_at,
            self.input_created_at,
            self.selection_selected_at,
            self.radar_observed_at,
            self.next_refresh_at,
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("market discovery audit timestamps must be timezone-aware")
        if self.radar_observed_at is not None and self.radar_observed_at > self.observed_at:
            raise ValueError("Radar snapshot cannot postdate discovery audit")
        if self.input_created_at is not None:
            if any(
                candidate.snapshot.as_of > self.input_created_at
                for candidate in self.candidates
            ):
                raise ValueError("market discovery audit cannot contain future candidates")
        if self.selection_selected_at is not None:
            if self.input_created_at is None:
                raise ValueError("selection_selected_at requires input_created_at")
            if self.selection_selected_at < self.input_created_at:
                raise ValueError("watchlist audit selection predates discovery input")
            if self.selection_selected_at > self.observed_at:
                raise ValueError("watchlist audit selection postdates observed_at")
        if self.candidate_market_count != len(self.candidates):
            raise ValueError("candidate_market_count must match persisted candidate facts")
        if self.radar_shortlist_market_count != len(self.radar_shortlist):
            raise ValueError("radar_shortlist_market_count must match Radar identities")

        if self.source == "RADAR_SHORTLIST":
            if self.candidates or self.selection_entries or self.selection_rationale is not None:
                raise ValueError("Radar discovery audit must not persist legacy Agent selection data")
            if self.status == "REFRESHED":
                if self.discovery_id is None or self.radar_observed_at is None:
                    raise ValueError("refreshed Radar audit requires Radar snapshot identity")
                if self.radar_status not in {RadarStatus.AVAILABLE, RadarStatus.PARTIAL}:
                    raise ValueError("refreshed Radar audit requires an admissible Radar status")
                if not self.radar_shortlist or not self.effective_watchlist:
                    raise ValueError("refreshed Radar audit requires a non-empty executable universe")
                radar_markets = set(self.radar_shortlist)
                if any(market not in radar_markets for market in self.effective_watchlist):
                    raise ValueError("Radar universe must remain inside the Radar shortlist")
            return self

        if self.radar_shortlist or self.radar_rejected_markets or self.radar_status is not None:
            raise ValueError("legacy discovery audit cannot carry Radar shortlist facts")
        if self.status == "REFRESHED":
            if self.discovery_id is None or self.input_created_at is None:
                raise ValueError("refreshed discovery audit requires discovery input identity")
            if self.selection_selected_at is None:
                raise ValueError("refreshed discovery audit requires selection timestamp")
            if not self.selection_entries or not self.selection_rationale:
                raise ValueError("refreshed discovery audit requires structured rationale")
            selected = tuple(entry.market for entry in self.selection_entries)
            if selected != self.effective_watchlist:
                raise ValueError("audit selection entries must equal effective watchlist")
            candidate_markets = {candidate.market for candidate in self.candidates}
            if any(market not in candidate_markets for market in selected):
                raise ValueError("audit watchlist must remain inside persisted candidates")
        return self


@dataclass(frozen=True, slots=True)
class MarketDiscoveryResult:
    watchlist: tuple[ExecutableMarket, ...]
    audit: MarketDiscoveryAudit


class WatchlistSelectingAgent(Protocol):
    async def select_watchlist(
        self,
        discovery_input: MarketDiscoveryInput,
    ) -> WatchlistSelection: ...


class RadarShortlistItem(Protocol):
    @property
    def market(self) -> ExecutableMarket: ...


class RadarShortlistOverview(Protocol):
    observed_at: datetime
    status: RadarStatus
    shortlist: tuple[RadarShortlistItem, ...]


class RadarShortlistReader(Protocol):
    @property
    def latest(self) -> RadarShortlistOverview: ...


class RadarUnavailableError(RuntimeError):
    pass


class RadarStaleError(RuntimeError):
    pass


class RadarEmptyShortlistError(RuntimeError):
    pass


class RadarNoExecutableCandidateError(RuntimeError):
    pass


class RadarSnapshotInvalidError(RuntimeError):
    pass


class MarketDiscoveryCoordinator:
    """Resolve the dynamic executable universe behind one canonical discovery boundary.

    Legacy mode preserves the historical Kraken research -> same-Agent watchlist flow.
    Radar mode consumes only typed market identities from the deterministic Market Attention
    shortlist, validates them against the executable Kraken catalogue/configuration, and never
    forwards Radar Analytics payloads to the strategic Agent.
    """

    def __init__(
        self,
        *,
        research: MarketResearchService,
        policy: MarketDiscoveryPolicy,
        settlement_asset: str,
        bootstrap_markets: tuple[ExecutableMarket, ...],
        aggressiveness: int,
        aggressiveness_context: AggressivenessContext,
        agent: WatchlistSelectingAgent | None = None,
        radar: RadarShortlistReader | None = None,
        radar_stale_after_seconds: float = DEFAULT_RADAR_STALE_AFTER_SECONDS,
        trading_style_context: TradingStyleContext | None = None,
        execution_cost_context: ExecutionCostContext | None = None,
        risk_allowed_pairs: frozenset[str] | None = None,
        clock: Clock | None = None,
    ) -> None:
        normalized_settlement = settlement_asset.strip().upper()
        if not normalized_settlement:
            raise ValueError("settlement_asset cannot be empty")
        if not bootstrap_markets:
            raise ValueError("market discovery requires bootstrap markets")
        if (agent is None) == (radar is None):
            raise ValueError("market discovery requires exactly one source: Agent or Radar")
        if isinstance(radar_stale_after_seconds, bool) or radar_stale_after_seconds <= 0:
            raise ValueError("radar_stale_after_seconds must be positive")
        for market in bootstrap_markets:
            _, quote = parse_canonical_symbol(market.symbol)
            if quote != normalized_settlement:
                raise ValueError("bootstrap market quote must equal settlement_asset")
            if market.market_type not in policy.market_types:
                raise ValueError("bootstrap market type must be enabled for discovery")
        self._research = research
        self._agent = agent
        self._radar = radar
        self._radar_stale_after_seconds = float(radar_stale_after_seconds)
        self._policy = policy
        self._settlement_asset = normalized_settlement
        self._bootstrap = _ordered_markets(bootstrap_markets)
        if (trading_style_context is None) != (execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        self._aggressiveness = aggressiveness
        self._aggressiveness_context = aggressiveness_context
        self._trading_style_context = trading_style_context
        self._execution_cost_context = execution_cost_context
        self._risk_allowed_pairs = risk_allowed_pairs
        self._clock = clock or SystemClock()
        self._catalogue: tuple[MarketResearchMarket, ...] = ()
        self._catalogue_refreshed_at: datetime | None = None
        self._probe_cursor = 0
        self._watchlist: tuple[ExecutableMarket, ...] = ()
        self._watchlist_refreshed_at: datetime | None = None
        self._watchlist_attempted_at: datetime | None = None
        self._last_audit: MarketDiscoveryAudit | None = None
        self._radar_observed_at: datetime | None = None
        self._radar_status: RadarStatus | None = None
        self._radar_shortlist: tuple[ExecutableMarket, ...] = ()
        self._radar_rejected_markets: tuple[ExecutableMarket, ...] = ()

    @property
    def source(self) -> DiscoverySource:
        return "RADAR_SHORTLIST" if self._radar is not None else "LEGACY_AGENT"

    @property
    def watchlist(self) -> tuple[ExecutableMarket, ...]:
        return self._watchlist

    @property
    def last_audit(self) -> MarketDiscoveryAudit | None:
        return self._last_audit

    def cache_result(
        self,
        *,
        status: Literal["CACHE_REUSED", "SKIPPED_MANAGEMENT"],
    ) -> MarketDiscoveryResult:
        now = self._now()
        effective = self._watchlist if self._radar is not None else (self._watchlist or self._bootstrap)
        audit = MarketDiscoveryAudit(
            source=self.source,
            status=status,
            observed_at=now,
            trading_style_context=self._trading_style_context,
            execution_cost_context=self._execution_cost_context,
            previous_watchlist=self._watchlist,
            effective_watchlist=effective,
            radar_observed_at=self._radar_observed_at,
            radar_status=self._radar_status,
            radar_shortlist_market_count=len(self._radar_shortlist),
            radar_shortlist=self._radar_shortlist,
            radar_rejected_markets=self._radar_rejected_markets,
            next_refresh_at=self._next_watchlist_refresh_at(),
        )
        self._last_audit = audit
        return MarketDiscoveryResult(watchlist=effective, audit=audit)

    async def refresh_if_due(
        self,
        *,
        portfolio_state: PortfolioState,
        force: bool = False,
    ) -> MarketDiscoveryResult:
        if self._radar is not None:
            return await self._refresh_from_radar(force=force)

        attempted_at = self._now()
        if not force and not self._watchlist_due(attempted_at):
            return self.cache_result(status="CACHE_REUSED")

        discovery_id = uuid4()
        previous = self._watchlist
        self._watchlist_attempted_at = attempted_at
        catalogue_refreshed = False
        compatible: tuple[MarketResearchMarket, ...] = ()
        probe: tuple[MarketResearchMarket, ...] = ()
        candidates: tuple[MarketCandidate, ...] = ()
        input_created_at: datetime | None = None
        try:
            async with asyncio.timeout(self._policy.refresh_timeout_seconds):
                if self._catalogue_due(attempted_at):
                    self._catalogue = await self._load_catalogue()
                    self._catalogue_refreshed_at = self._now()
                    catalogue_refreshed = True

                compatible = self._compatible_catalogue(self._catalogue)
                probe = self._next_probe(compatible)
                candidates = await self._build_candidates(probe)
                if not candidates:
                    raise RuntimeError("market discovery produced no factual candidate")

                input_created_at = self._now()
                discovery_input = MarketDiscoveryInput(
                    discovery_id=discovery_id,
                    created_at=input_created_at,
                    portfolio_state=portfolio_state,
                    candidates=candidates,
                    previous_watchlist=previous,
                    watchlist_limit=self._policy.watchlist_limit,
                    aggressiveness=self._aggressiveness,
                    aggressiveness_context=self._aggressiveness_context,
                    trading_style_context=self._trading_style_context,
                    execution_cost_context=self._execution_cost_context,
                    market_discovery_context={
                        "protocol_version": MARKET_DISCOVERY_PROTOCOL_VERSION,
                        "instruction": (
                            "Selectionne entre 1 et watchlist_limit marches strategiquement "
                            "interessants uniquement parmi candidates. La selection constitue une "
                            "watchlist de surveillance et ne declenche aucun ordre. Les faits de "
                            "candidate sont descriptifs; n'invente aucun marche ni aucune donnee."
                        ),
                    },
                )
                assert self._agent is not None
                selection = await self._agent.select_watchlist(discovery_input)
                self._validate_selection(discovery_input, selection)
                completed_at = self._now()
                if selection.selected_at > completed_at:
                    raise ValueError("watchlist selection cannot postdate discovery completion")
                self._watchlist = selection.markets
                self._watchlist_refreshed_at = completed_at
                added, maintained, removed = _diff(previous, self._watchlist)
                audit = MarketDiscoveryAudit(
                    discovery_id=discovery_id,
                    status="REFRESHED",
                    observed_at=completed_at,
                    trading_style_context=self._trading_style_context,
                    execution_cost_context=self._execution_cost_context,
                    catalogue_refreshed=catalogue_refreshed,
                    catalogue_market_count=len(self._catalogue),
                    compatible_market_count=len(compatible),
                    probed_market_count=len(probe),
                    candidate_market_count=len(candidates),
                    input_created_at=input_created_at,
                    candidates=candidates,
                    selection_selected_at=selection.selected_at,
                    previous_watchlist=previous,
                    effective_watchlist=self._watchlist,
                    added_markets=added,
                    maintained_markets=maintained,
                    removed_markets=removed,
                    selection_rationale=selection.rationale,
                    selection_entries=selection.entries,
                    next_refresh_at=self._next_watchlist_refresh_at(),
                )
                self._last_audit = audit
                return MarketDiscoveryResult(watchlist=self._watchlist, audit=audit)
        except Exception as exc:
            completed_at = self._now()
            effective = previous or self._bootstrap
            self._watchlist_refreshed_at = completed_at
            audit = MarketDiscoveryAudit(
                discovery_id=discovery_id,
                status="FALLBACK",
                observed_at=completed_at,
                trading_style_context=self._trading_style_context,
                execution_cost_context=self._execution_cost_context,
                catalogue_refreshed=catalogue_refreshed,
                catalogue_market_count=len(self._catalogue),
                compatible_market_count=len(compatible),
                probed_market_count=len(probe),
                candidate_market_count=len(candidates),
                input_created_at=input_created_at,
                candidates=candidates,
                previous_watchlist=previous,
                effective_watchlist=effective,
                maintained_markets=tuple(market for market in effective if market in previous),
                error_type=type(exc).__name__,
                next_refresh_at=self._next_watchlist_refresh_at(),
            )
            self._last_audit = audit
            return MarketDiscoveryResult(watchlist=effective, audit=audit)

    async def _refresh_from_radar(self, *, force: bool) -> MarketDiscoveryResult:
        attempted_at = self._now()
        discovery_id = uuid4()
        previous = self._watchlist
        self._watchlist_attempted_at = attempted_at
        catalogue_refreshed = False
        compatible: tuple[MarketResearchMarket, ...] = ()
        radar_observed_at: datetime | None = None
        radar_status: RadarStatus | None = None
        radar_shortlist: tuple[ExecutableMarket, ...] = ()
        rejected: tuple[ExecutableMarket, ...] = ()
        try:
            async with asyncio.timeout(self._policy.refresh_timeout_seconds):
                assert self._radar is not None
                overview = self._radar.latest
                raw_observed_at = overview.observed_at
                if raw_observed_at.tzinfo is None or raw_observed_at.utcoffset() is None:
                    raise RadarSnapshotInvalidError(
                        "Radar observed_at must be timezone-aware"
                    )
                radar_observed_at = raw_observed_at.astimezone(UTC)
                radar_status = RadarStatus(overview.status)
                self._validate_radar_overview(
                    observed_at=radar_observed_at,
                    status=radar_status,
                    now=attempted_at,
                )
                radar_shortlist = tuple(item.market for item in overview.shortlist)
                if not radar_shortlist:
                    raise RadarEmptyShortlistError("Radar shortlist is empty")

                if (
                    not force
                    and self._radar_observed_at == radar_observed_at
                    and not self._catalogue_due(attempted_at)
                    and self._watchlist
                ):
                    self._watchlist_attempted_at = attempted_at
                    return self.cache_result(status="CACHE_REUSED")

                if self._catalogue_due(attempted_at):
                    self._catalogue = await self._load_catalogue()
                    self._catalogue_refreshed_at = self._now()
                    catalogue_refreshed = True

                compatible = self._compatible_catalogue(self._catalogue)
                executable = {
                    ExecutableMarket(symbol=item.symbol, market_type=item.market_type)
                    for item in compatible
                }
                accepted: list[ExecutableMarket] = []
                rejected_list: list[ExecutableMarket] = []
                seen: set[ExecutableMarket] = set()
                for market in radar_shortlist:
                    if market in seen:
                        continue
                    seen.add(market)
                    if market not in executable:
                        rejected_list.append(market)
                        continue
                    accepted.append(market)
                    if len(accepted) >= self._policy.watchlist_limit:
                        break
                rejected = tuple(rejected_list)
                if not accepted:
                    raise RadarNoExecutableCandidateError(
                        "Radar shortlist contains no executable campaign candidate"
                    )

                completed_at = self._now()
                self._watchlist = _ordered_markets(tuple(accepted))
                self._watchlist_refreshed_at = completed_at
                self._radar_observed_at = radar_observed_at
                self._radar_status = radar_status
                self._radar_shortlist = radar_shortlist
                self._radar_rejected_markets = rejected
                added, maintained, removed = _diff(previous, self._watchlist)
                audit = MarketDiscoveryAudit(
                    source="RADAR_SHORTLIST",
                    discovery_id=discovery_id,
                    status="REFRESHED",
                    observed_at=completed_at,
                    trading_style_context=self._trading_style_context,
                    execution_cost_context=self._execution_cost_context,
                    catalogue_refreshed=catalogue_refreshed,
                    catalogue_market_count=len(self._catalogue),
                    compatible_market_count=len(compatible),
                    previous_watchlist=previous,
                    effective_watchlist=self._watchlist,
                    added_markets=added,
                    maintained_markets=maintained,
                    removed_markets=removed,
                    radar_observed_at=radar_observed_at,
                    radar_status=radar_status,
                    radar_shortlist_market_count=len(radar_shortlist),
                    radar_shortlist=radar_shortlist,
                    radar_rejected_markets=rejected,
                    next_refresh_at=self._next_watchlist_refresh_at(),
                )
                self._last_audit = audit
                return MarketDiscoveryResult(watchlist=self._watchlist, audit=audit)
        except Exception as exc:
            completed_at = self._now()
            self._watchlist = ()
            self._watchlist_refreshed_at = completed_at
            self._radar_observed_at = radar_observed_at
            self._radar_status = radar_status
            self._radar_shortlist = radar_shortlist
            self._radar_rejected_markets = rejected
            audit = MarketDiscoveryAudit(
                source="RADAR_SHORTLIST",
                discovery_id=discovery_id,
                status="FALLBACK",
                observed_at=completed_at,
                trading_style_context=self._trading_style_context,
                execution_cost_context=self._execution_cost_context,
                catalogue_refreshed=catalogue_refreshed,
                catalogue_market_count=len(self._catalogue),
                compatible_market_count=len(compatible),
                previous_watchlist=previous,
                effective_watchlist=(),
                removed_markets=previous,
                radar_observed_at=radar_observed_at,
                radar_status=radar_status,
                radar_shortlist_market_count=len(radar_shortlist),
                radar_shortlist=radar_shortlist,
                radar_rejected_markets=rejected,
                error_type=type(exc).__name__,
                next_refresh_at=self._next_watchlist_refresh_at(),
            )
            self._last_audit = audit
            return MarketDiscoveryResult(watchlist=(), audit=audit)

    def _validate_radar_overview(
        self,
        *,
        observed_at: datetime,
        status: RadarStatus,
        now: datetime,
    ) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise RadarSnapshotInvalidError("Radar observed_at must be timezone-aware")
        if observed_at > now:
            raise RadarSnapshotInvalidError("Radar snapshot cannot come from the future")
        age_seconds = (now - observed_at).total_seconds()
        if status is RadarStatus.STALE or age_seconds > self._radar_stale_after_seconds:
            raise RadarStaleError("Radar snapshot is stale")
        if status not in {RadarStatus.AVAILABLE, RadarStatus.PARTIAL}:
            raise RadarUnavailableError(f"Radar status {status.value} is not usable")

    async def _load_catalogue(self) -> tuple[MarketResearchMarket, ...]:
        found: list[MarketResearchMarket] = []
        for market_type in self._policy.market_types:
            cursor = 0
            while True:
                page = await self._research.list_markets(
                    market_type=market_type,
                    cursor=cursor,
                    limit=self._research.max_list_limit,
                )
                found.extend(page.markets)
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor
        ordered = tuple(
            sorted(
                found,
                key=lambda item: (item.market_type.value, item.symbol, item.venue_symbol),
            )
        )
        return ordered

    def _compatible_catalogue(
        self,
        catalogue: tuple[MarketResearchMarket, ...],
    ) -> tuple[MarketResearchMarket, ...]:
        compatible: list[MarketResearchMarket] = []
        seen_addresses: set[tuple[str, MarketType]] = set()
        allowed_statuses = {"online", "open", "active", "tradeable", "tradable"}
        for item in catalogue:
            if item.market_type not in self._policy.market_types:
                continue
            if item.market_type is MarketType.FUTURE:
                continue
            if item.quote_asset != self._settlement_asset:
                continue
            if item.status is not None and item.status.strip().lower() not in allowed_statuses:
                continue
            if (
                item.market_type is MarketType.PERPETUAL
                and item.contract_kind is not DerivativeContractKind.LINEAR
            ):
                continue
            if self._risk_allowed_pairs is not None and item.symbol not in self._risk_allowed_pairs:
                continue
            address = (item.symbol, item.market_type)
            if address in seen_addresses:
                continue
            seen_addresses.add(address)
            compatible.append(item)
        return tuple(compatible)

    def _next_probe(
        self,
        compatible: tuple[MarketResearchMarket, ...],
    ) -> tuple[MarketResearchMarket, ...]:
        if not compatible:
            return ()
        count = min(len(compatible), self._policy.candidate_probe_limit)
        start = self._probe_cursor % len(compatible)
        indices = tuple((start + offset) % len(compatible) for offset in range(count))
        self._probe_cursor = (start + count) % len(compatible)
        selected = [compatible[index] for index in indices]
        return tuple(selected)

    async def _build_candidates(
        self,
        probe: tuple[MarketResearchMarket, ...],
    ) -> tuple[MarketCandidate, ...]:
        candidates: list[MarketCandidate] = []
        for item in probe:
            try:
                snapshot = await self._research.get_market_snapshot(
                    symbol=item.symbol,
                    market_type=item.market_type,
                )
            except Exception:
                continue
            if not self._snapshot_is_admissible(snapshot, created_at=self._now()):
                continue
            candidates.append(
                MarketCandidate(
                    market=ExecutableMarket(symbol=item.symbol, market_type=item.market_type),
                    status=item.status,
                    venue_symbol=item.venue_symbol,
                    snapshot=snapshot,
                )
            )
            if len(candidates) >= self._policy.candidate_limit:
                break
        return tuple(
            sorted(candidates, key=lambda item: (item.market.market_type.value, item.market.symbol))
        )

    def _snapshot_is_admissible(
        self,
        snapshot: MarketResearchSnapshot,
        *,
        created_at: datetime,
    ) -> bool:
        if snapshot.as_of > created_at:
            return False
        context = snapshot.context
        observed_at = snapshot.as_of if context is None else context.last_observed_at
        if observed_at > created_at:
            return False
        age = Decimal(str((created_at - observed_at).total_seconds()))
        if age > Decimal(self._policy.max_snapshot_age_seconds):
            return False
        if context is None:
            return self._policy.min_window_observations == 0
        if context.is_stale is True:
            return False
        if self._policy.min_window_observations == 0 and not self._policy.require_complete_window:
            return True
        for window in context.windows:
            if window.last_observed_at is not None and window.last_observed_at > created_at:
                return False
            if window.observation_count < self._policy.min_window_observations:
                continue
            if self._policy.require_complete_window and not window.is_complete:
                continue
            return True
        return False

    def _validate_selection(
        self,
        discovery_input: MarketDiscoveryInput,
        selection: WatchlistSelection,
    ) -> None:
        if selection.discovery_id != discovery_input.discovery_id:
            raise ValueError("watchlist discovery_id mismatch")
        if selection.selected_at < discovery_input.created_at:
            raise ValueError("watchlist selection predates discovery input")
        if len(selection.entries) > discovery_input.watchlist_limit:
            raise ValueError("watchlist selection exceeds configured limit")
        candidates = {item.market for item in discovery_input.candidates}
        if any(entry.market not in candidates for entry in selection.entries):
            raise ValueError("Agent selected a market outside the candidate universe")

    def _catalogue_due(self, now: datetime) -> bool:
        if not self._catalogue or self._catalogue_refreshed_at is None:
            return True
        return now - self._catalogue_refreshed_at >= timedelta(
            seconds=self._policy.catalog_refresh_seconds
        )

    def _watchlist_due(self, now: datetime) -> bool:
        anchor = self._watchlist_refreshed_at or self._watchlist_attempted_at
        if anchor is None:
            return True
        return now - anchor >= timedelta(
            seconds=self._policy.watchlist_refresh_seconds
        )

    def _next_watchlist_refresh_at(self) -> datetime | None:
        anchor = self._watchlist_refreshed_at or self._watchlist_attempted_at
        if anchor is None:
            return None
        return anchor + timedelta(
            seconds=self._policy.watchlist_refresh_seconds
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("market discovery clock must be timezone-aware")
        return value.astimezone(UTC)


def _ordered_markets(markets: tuple[ExecutableMarket, ...]) -> tuple[ExecutableMarket, ...]:
    ordered = tuple(sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol)))
    if not ordered:
        raise ValueError("market set cannot be empty")
    return ordered


def _diff(
    previous: tuple[ExecutableMarket, ...],
    current: tuple[ExecutableMarket, ...],
) -> tuple[
    tuple[ExecutableMarket, ...],
    tuple[ExecutableMarket, ...],
    tuple[ExecutableMarket, ...],
]:
    previous_set = set(previous)
    current_set = set(current)
    key = lambda item: (item.market_type.value, item.symbol)
    added = tuple(sorted(current_set - previous_set, key=key))
    maintained = tuple(sorted(current_set & previous_set, key=key))
    removed = tuple(sorted(previous_set - current_set, key=key))
    return added, maintained, removed
