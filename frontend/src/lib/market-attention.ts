export type RadarStatus = "AVAILABLE" | "PARTIAL" | "NOT_CONFIGURED" | "STALE" | "ERROR";
export type MarketActivityState = "UNKNOWN" | "NORMAL" | "ELEVATED" | "ACCELERATING" | "VERY_HIGH";
export type PublicAttentionDirection = "UNKNOWN" | "FALLING" | "STABLE" | "RISING";
export type CrossAttentionState = "NORMAL" | "MARKET_ONLY" | "PUBLIC_ONLY" | "CONVERGING";
export type AttentionLevel = "NORMAL" | "MEDIUM" | "HIGH";
export type AttentionTimeframe = "5m" | "15m" | "1h" | "4h";

export type AttentionMarket = {
  symbol: string;
  market_type: "SPOT" | "PERPETUAL";
};

export type ActivityHorizonSnapshot = {
  timeframe: AttentionTimeframe;
  current_volume: string | null;
  previous_comparable_volume: string | null;
  baseline_volume: string | null;
  volume_ratio: string | null;
  volume_change: string | null;
  volume_acceleration: string | null;
  price_return: string | null;
  price_range: string | null;
  realized_volatility: string | null;
  observation_count: number;
  baseline_period_count: number;
  complete: boolean;
};

export type MarketActivitySnapshot = {
  market: AttentionMarket;
  observed_at: string;
  status: RadarStatus;
  activity_state: MarketActivityState;
  freshness_seconds: string | null;
  horizons: ActivityHorizonSnapshot[];
  error_type: string | null;
};

export type ActivityStatusCounts = {
  AVAILABLE: number;
  PARTIAL: number;
  STALE: number;
  ERROR: number;
};

export type ActivityStateCounts = Record<MarketActivityState, number>;

export type SubthresholdActivitySnapshot = {
  market: AttentionMarket;
  peak_volume_ratio: string;
  peak_timeframe: AttentionTimeframe;
};

export type PublicAttentionSource = {
  title: string;
  url: string;
  source_domain: string;
  observed_at: string;
  published_at: string | null;
};

export type PublicAttentionMetric = {
  name: string;
  value: string;
  unit: string | null;
  window: string | null;
  source_url: string | null;
  observed_at: string;
  published_at: string | null;
};

export type PublicAttentionObservation = {
  text: string;
  source_url: string | null;
};

export type PublicAttentionCatalyst = {
  description: string;
  source_url: string | null;
};

export type PublicAttentionSnapshot = {
  asset: string;
  observed_at: string;
  research_status: RadarStatus;
  attention_direction: PublicAttentionDirection;
  quantitative_metrics: PublicAttentionMetric[];
  qualitative_observations: PublicAttentionObservation[];
  possible_catalysts: PublicAttentionCatalyst[];
  sources: PublicAttentionSource[];
  confidence_context: string;
  error_type: string | null;
};

export type MarketAttentionSnapshot = {
  market_activity: MarketActivitySnapshot;
  public_attention: PublicAttentionSnapshot;
  cross_state: CrossAttentionState;
  attention_level: AttentionLevel;
};

export type MarketAttentionOverview = {
  protocol_version: "market-attention-radar-v1";
  observed_at: string;
  status: RadarStatus;
  informative_only: true;
  catalogue_market_count: number;
  cached_activity_market_count: number;
  scanned_market_count: number;
  candidate_market_count: number;
  web_search_count: number;
  activity_status_counts: ActivityStatusCounts;
  activity_state_counts: ActivityStateCounts;
  subthreshold_activity: SubthresholdActivitySnapshot[];
  shortlist: MarketAttentionSnapshot[];
  error_type: string | null;
};

export function attentionHorizon(
  item: MarketAttentionSnapshot,
  timeframe: AttentionTimeframe,
): ActivityHorizonSnapshot | null {
  return item.market_activity.horizons.find((entry) => entry.timeframe === timeframe) ?? null;
}

export function citedPublicSources(item: MarketAttentionSnapshot): PublicAttentionSource[] {
  const seen = new Set<string>();
  return item.public_attention.sources.filter((source) => {
    if (!source.url.startsWith("http://") && !source.url.startsWith("https://")) return false;
    if (seen.has(source.url)) return false;
    seen.add(source.url);
    return true;
  });
}

export function formatVolumeRatio(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return `${parsed.toFixed(parsed >= 10 ? 1 : 2)}×`;
}

export function formatSignedPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const percent = parsed * 100;
  return `${percent > 0 ? "+" : ""}${percent.toFixed(2)} %`;
}

export function marketAttentionStatusMessage(overview: MarketAttentionOverview): string {
  if (overview.status === "NOT_CONFIGURED") return "Radar non configuré.";
  if (overview.status === "ERROR") return "Radar en erreur — consulter le diagnostic backend.";
  if (overview.status === "STALE") return "Radar opérationnel mais données d’activité périmées.";
  if (overview.status === "PARTIAL") {
    return overview.candidate_market_count > 0
      ? "Radar partiellement disponible — certains enrichissements ou marchés sont dégradés."
      : "Radar partiellement disponible — aucune activité inhabituelle confirmée sur les données exploitables.";
  }
  if (overview.candidate_market_count === 0) {
    const degradedCount =
      overview.activity_status_counts.PARTIAL
      + overview.activity_status_counts.STALE
      + overview.activity_status_counts.ERROR;
    return degradedCount > 0
      ? "Radar opérationnel — aucun événement inhabituel détecté sur les marchés disponibles."
      : "Radar opérationnel — aucun événement inhabituel détecté.";
  }
  return `Radar opérationnel — ${overview.candidate_market_count} candidat${overview.candidate_market_count > 1 ? "s" : ""} d’attention.`;
}

export async function fetchMarketAttention(signal?: AbortSignal): Promise<MarketAttentionOverview> {
  const response = await fetch("/backend/api/v1/market-attention", {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Radar backend indisponible (${response.status})`);
  return (await response.json()) as MarketAttentionOverview;
}
