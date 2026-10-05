"use client";

import { BarChart3, RefreshCw, X } from "lucide-react";
import { useCallback, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type ScoreDistribution = {
  score_0: number;
  score_1: number;
  score_2: number;
  score_3: number;
  score_4: number;
};

type ComponentContributions = {
  OPEN_INTEREST: number;
  FUNDING: number;
  LIQUIDATION_VOLUME: number;
  ORDER_FLOW: number;
};

type StatusCounts = {
  AVAILABLE: number;
  PARTIAL: number;
  INSUFFICIENT_HISTORY: number;
  STALE: number;
  TECHNICAL_ERROR: number;
  NOT_APPLICABLE: number;
  UNAVAILABLE: number;
};

type SeriesHealth = {
  series: string;
  observations: number;
  statuses: StatusCounts;
  available_ratio: number | null;
  partial_ratio: number | null;
  insufficient_history_ratio: number | null;
  stale_ratio: number | null;
  technical_error_ratio: number | null;
};

type RankChangeBucket = {
  rank_change: number;
  count: number;
};

type ScopeObservability = {
  scope: string;
  snapshots_observed: number;
  perpetual_candidates_observed: number;
  ranking_candidates_observed: number;
  mean_score: number | null;
  reranking_applicable_snapshots: number;
  effective_reranking_snapshots: number;
};

type MarketCoverage = {
  market_type: string;
  symbol: string;
  candidate_observations: number;
  ranking_observations: number;
  observations_with_any_available_series: number;
  analytics_available_ratio: number | null;
  mean_score: number | null;
  effective_rank_changes: number;
};

type AnalyticsRankingObservability = {
  schema_version: string;
  source: string;
  requested_history_limit: number;
  source_snapshot_count: number;
  snapshots_observed: number;
  legacy_snapshots_ignored: number;
  window_started_at: string | null;
  window_ended_at: string | null;
  score_distribution: ScoreDistribution;
  component_contributions: ComponentContributions;
  series_status_totals: StatusCounts;
  series_health: SeriesHealth[];
  perpetual_candidates_observed: number;
  ranking_candidates_observed: number;
  perpetual_candidates_missing_ranking: number;
  perpetual_candidates_without_usable_analytics: number;
  perpetual_candidates_without_usable_analytics_ratio: number | null;
  reranking_applicable_snapshots: number;
  effective_reranking_snapshots: number;
  reranking_effective_ratio: number | null;
  analytics_applicable_but_no_rank_change_snapshots: number;
  candidates_moved_up: number;
  candidates_moved_down: number;
  candidates_unchanged: number;
  rank_change_missing_candidates: number;
  rank_change_observation_count: number;
  rank_change_distribution: RankChangeBucket[];
  mean_absolute_rank_change: number | null;
  max_absolute_rank_change: number | null;
  order_flow_deduplications: number;
  order_flow_deduplication_ratio: number | null;
  order_flow_conflicts: number;
  order_flow_conflict_ratio: number | null;
  scope_breakdown: ScopeObservability[];
  market_coverage: MarketCoverage[];
};

function percent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)} %`;
}

function decimal(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function shortDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/10 p-2.5">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[10px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value}</span>
    </div>
  );
}

async function fetchObservability(signal?: AbortSignal): Promise<AnalyticsRankingObservability> {
  const response = await fetch("/backend/api/v1/market-attention/observability?limit=96", {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`Observabilité Analytics indisponible (${response.status})`);
  }
  return (await response.json()) as AnalyticsRankingObservability;
}

export function AnalyticsRankingObservabilityDock() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<AnalyticsRankingObservability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchObservability());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, []);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next && data === null && !loading) void refresh();
  }

  const scores = data
    ? [
        ["0", data.score_distribution.score_0],
        ["1", data.score_distribution.score_1],
        ["2", data.score_distribution.score_2],
        ["3", data.score_distribution.score_3],
        ["4", data.score_distribution.score_4],
      ] as const
    : [];

  const components = data
    ? [
        ["Open Interest", data.component_contributions.OPEN_INTEREST],
        ["Funding", data.component_contributions.FUNDING],
        ["Liquidations", data.component_contributions.LIQUIDATION_VOLUME],
        ["Order flow", data.component_contributions.ORDER_FLOW],
      ] as const
    : [];

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={toggleOpen}
        className="fixed bottom-5 left-5 z-50 shadow-xl"
        aria-expanded={open}
      >
        <BarChart3 className="size-4" /> Analytics obs.
      </Button>

      {open ? (
        <Card className="fixed bottom-20 left-3 z-50 max-h-[74vh] w-[min(96vw,900px)] overflow-hidden shadow-2xl sm:left-5">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="size-4" /> Observabilité ranking Analytics
                  </CardTitle>
                  <Badge tone="info">DESCRIPTIF · CAUSAL · SANS P&amp;L FUTUR</Badge>
                </div>
                <CardDescription className="mt-1">
                  Agrégation à la demande de l’historique Radar borné. Aucun poids, seuil, candidat,
                  interest_level, Agent, Risk Engine ou Broker n’est modifié par cette vue.
                </CardDescription>
              </div>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading} aria-label="Actualiser l’observabilité">
                  <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setOpen(false)} aria-label="Fermer l’observabilité">
                  <X className="size-3.5" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="max-h-[calc(74vh-105px)] overflow-y-auto py-4">
            {error ? (
              <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground">
                {error}
              </div>
            ) : null}

            {data ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground">
                  <span>
                    Fenêtre {shortDate(data.window_started_at)} → {shortDate(data.window_ended_at)} · {data.snapshots_observed} snapshot(s) Analytics / {data.source_snapshot_count} retenu(s)
                  </span>
                  <span>
                    Limite {data.requested_history_limit} · legacy ignorés {data.legacy_snapshots_ignored}
                  </span>
                </div>

                <div className="grid gap-3 lg:grid-cols-2">
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Distribution récente du score</p>
                    <div className="mt-2 grid grid-cols-5 gap-2">
                      {scores.map(([score, count]) => (
                        <Metric key={score} label={`Score ${score}`} value={String(count)} />
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Reranking effectif</p>
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Metric label="Applicable" value={String(data.reranking_applicable_snapshots)} />
                      <Metric label="Avec mouvement" value={String(data.effective_reranking_snapshots)} />
                      <Metric label="Taux effectif" value={percent(data.reranking_effective_ratio)} />
                      <Metric label="Applicable sans mouvement" value={String(data.analytics_applicable_but_no_rank_change_snapshots)} />
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-2">
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Contribution des familles</p>
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {components.map(([label, count]) => (
                        <Metric key={label} label={label} value={String(count)} />
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Amplitude des changements de rang</p>
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Metric label="Montés" value={String(data.candidates_moved_up)} />
                      <Metric label="Descendus" value={String(data.candidates_moved_down)} />
                      <Metric label="Inchangés" value={String(data.candidates_unchanged)} />
                      <Metric label="|Δ rang| moyen / max" value={`${decimal(data.mean_absolute_rank_change)} / ${data.max_absolute_rank_change ?? "—"}`} />
                    </div>
                    <p className="mt-2 text-[10px] text-muted-foreground">
                      Distribution Δ rang : {data.rank_change_distribution.length
                        ? data.rank_change_distribution.map((bucket) => `${bucket.rank_change > 0 ? "+" : ""}${bucket.rank_change}:${bucket.count}`).join(" · ")
                        : "—"}
                    </p>
                  </div>
                </div>

                <div className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-xs font-semibold">Santé des cinq séries</p>
                    <p className="text-[10px] text-muted-foreground">
                      PERP sans série AVAILABLE : {data.perpetual_candidates_without_usable_analytics}/{data.perpetual_candidates_observed} ({percent(data.perpetual_candidates_without_usable_analytics_ratio)})
                    </p>
                  </div>
                  <div className="mt-2 grid gap-2 md:grid-cols-5">
                    {data.series_health.map((series) => (
                      <div key={series.series} className="rounded-md border bg-muted/10 p-2.5">
                        <p className="truncate text-[10px] font-semibold uppercase tracking-wide">{series.series}</p>
                        <p className="mt-1 font-mono text-xs font-semibold">AVAILABLE {percent(series.available_ratio)}</p>
                        <div className="mt-2 space-y-1">
                          <StatusLine label="AVAILABLE" value={series.statuses.AVAILABLE} />
                          <StatusLine label="PARTIAL" value={series.statuses.PARTIAL} />
                          <StatusLine label="INSUFF." value={series.statuses.INSUFFICIENT_HISTORY} />
                          <StatusLine label="STALE" value={series.statuses.STALE} />
                          <StatusLine label="ERROR" value={series.statuses.TECHNICAL_ERROR} />
                          <StatusLine label="N/A" value={series.statuses.NOT_APPLICABLE} />
                          <StatusLine label="UNAVAILABLE" value={series.statuses.UNAVAILABLE} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-2">
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Order flow</p>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <Metric label="Déduplications CVD/Aggressor" value={`${data.order_flow_deduplications} · ${percent(data.order_flow_deduplication_ratio)}`} />
                      <Metric label="Conflits CVD/Aggressor" value={`${data.order_flow_conflicts} · ${percent(data.order_flow_conflict_ratio)}`} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold">Scopes observés</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                      {data.scope_breakdown.map((scope) => (
                        <div key={scope.scope} className="rounded-md border bg-muted/10 p-2.5 text-[10px]">
                          <p className="font-semibold">{scope.scope}</p>
                          <p className="mt-1 text-muted-foreground">Snapshots {scope.snapshots_observed}</p>
                          <p className="text-muted-foreground">PERP {scope.perpetual_candidates_observed}</p>
                          <p className="text-muted-foreground">Score moyen {decimal(scope.mean_score)}</p>
                          <p className="text-muted-foreground">Rerank {scope.effective_reranking_snapshots}/{scope.reranking_applicable_snapshots}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {data.market_coverage.length ? (
                  <div className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <p className="text-xs font-semibold">Couverture par marché</p>
                      <p className="text-[10px] text-muted-foreground">Affichage compact des 10 premiers marchés, tri backend déterministe.</p>
                    </div>
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {data.market_coverage.slice(0, 10).map((market) => (
                        <div key={`${market.market_type}:${market.symbol}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/15 px-2.5 py-2 text-[10px]">
                          <div>
                            <span className="font-semibold">{market.symbol}</span>
                            <span className="ml-1 text-muted-foreground">{market.market_type}</span>
                          </div>
                          <span className="font-mono tabular-nums text-muted-foreground">
                            n={market.candidate_observations} · dispo {percent(market.analytics_available_ratio)} · score μ {decimal(market.mean_score)} · Δ {market.effective_rank_changes}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                <p className="text-[10px] text-muted-foreground">
                  Cette vue ne mesure aucune rentabilité et ne relie pas le ranking à des mouvements futurs. La fenêtre est process-locale : un redémarrage backend vide l’historique Radar en mémoire. Le Batch 48 n’ajoute aucune base, aucun journal durable et aucune calibration automatique.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{loading ? "Calcul de l’observabilité…" : "Aucune observation chargée."}</p>
            )}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
