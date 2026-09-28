"use client";

import { ExternalLink, Radar, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  attentionHorizon,
  citedPublicSources,
  fetchMarketAttention,
  formatSignedPercent,
  formatVolumeRatio,
  type MarketAttentionOverview,
  type MarketAttentionSnapshot,
  type RadarStatus,
} from "@/lib/market-attention";

function statusTone(status: RadarStatus) {
  if (status === "AVAILABLE") return "success" as const;
  if (status === "PARTIAL" || status === "STALE") return "warning" as const;
  if (status === "ERROR") return "danger" as const;
  return "neutral" as const;
}

function attentionTone(level: MarketAttentionSnapshot["attention_level"]) {
  if (level === "HIGH") return "warning" as const;
  if (level === "MEDIUM") return "info" as const;
  return "neutral" as const;
}

function freshness(value: string | null) {
  if (value === null) return "—";
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function shortTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  }).format(parsed);
}

function MarketRow({ item, expanded, onToggle }: { item: MarketAttentionSnapshot; expanded: boolean; onToggle: () => void }) {
  const h5 = attentionHorizon(item, "5m");
  const h15 = attentionHorizon(item, "15m");
  const h1 = attentionHorizon(item, "1h");
  const sources = citedPublicSources(item);
  const priceMove = h15?.price_return ?? h5?.price_return ?? null;
  const catalyst = item.public_attention.possible_catalysts[0]?.description ?? item.public_attention.qualitative_observations[0]?.text ?? null;

  return (
    <div className="rounded-xl border bg-background/70">
      <button type="button" onClick={onToggle} className="grid w-full gap-3 p-3 text-left md:grid-cols-[minmax(140px,1.15fr)_repeat(7,minmax(70px,0.7fr))] md:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{item.market_activity.market.symbol}</span>
            <Badge tone="neutral">{item.market_activity.market.market_type}</Badge>
            <Badge tone={attentionTone(item.attention_level)}>{item.attention_level}</Badge>
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">{item.cross_state.replaceAll("_", " ")}</p>
        </div>
        <Fact label="Marché" value={item.market_activity.activity_state.replaceAll("_", " ")} />
        <Fact label="Public" value={item.public_attention.attention_direction} />
        <Fact label="Vol. 5m" value={formatVolumeRatio(h5?.volume_ratio)} />
        <Fact label="Vol. 15m" value={formatVolumeRatio(h15?.volume_ratio)} />
        <Fact label="Vol. 1h" value={formatVolumeRatio(h1?.volume_ratio)} />
        <Fact label="Prix" value={formatSignedPercent(priceMove)} />
        <Fact label="Sources" value={String(sources.length)} />
      </button>

      {expanded ? (
        <div className="space-y-4 border-t px-3 py-4 text-xs">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Fact label="Fraîcheur marché" value={freshness(item.market_activity.freshness_seconds)} />
            <Fact label="Dernière recherche" value={shortTime(item.public_attention.observed_at)} />
            <Fact label="Recherche web" value={item.public_attention.research_status} />
            <Fact label="État croisé" value={item.cross_state.replaceAll("_", " ")} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border bg-muted/15 p-3">
              <p className="font-semibold">Contexte / catalyseur</p>
              <p className="mt-1 leading-relaxed text-muted-foreground">{catalyst ?? "Aucun catalyseur public fiable n’a été structuré."}</p>
              <p className="mt-2 border-t pt-2 leading-relaxed text-muted-foreground">{item.public_attention.confidence_context}</p>
            </div>
            <div className="rounded-lg border bg-muted/15 p-3">
              <p className="font-semibold">Métriques publiques observées</p>
              {item.public_attention.quantitative_metrics.length ? (
                <div className="mt-2 space-y-1.5">
                  {item.public_attention.quantitative_metrics.slice(0, 6).map((metric, index) => (
                    <div key={`${metric.name}-${index}`} className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="text-muted-foreground">{metric.name}{metric.window ? ` · ${metric.window}` : ""}</span>
                      <strong>{metric.value}{metric.unit ? ` ${metric.unit}` : ""}</strong>
                    </div>
                  ))}
                </div>
              ) : <p className="mt-1 text-muted-foreground">Aucun chiffre public fiable disponible ; le qualitatif n’est pas transformé en faux score.</p>}
            </div>
          </div>

          <div>
            <p className="font-semibold">Sources publiques</p>
            {sources.length ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {sources.map((source) => (
                  <a key={source.url} href={source.url} target="_blank" rel="noreferrer noopener" className="flex min-w-0 items-start gap-2 rounded-lg border p-2 hover:bg-muted/30">
                    <ExternalLink className="mt-0.5 size-3.5 shrink-0" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{source.title}</span>
                      <span className="block truncate text-[10px] text-muted-foreground">{source.source_domain} · {shortTime(source.published_at ?? source.observed_at)}</span>
                    </span>
                  </a>
                ))}
              </div>
            ) : <p className="mt-1 text-muted-foreground">Aucune citation publique exploitable retournée.</p>}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 truncate font-mono text-[11px] font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export function MarketAttentionDock() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<MarketAttentionOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const next = await fetchMarketAttention(signal);
      setData(next);
      setError(null);
    } catch (caught) {
      if (signal?.aborted) return;
      setError(caught instanceof Error ? caught.message : "Radar indisponible");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const interval = window.setInterval(() => void refresh(controller.signal), 60_000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [open, refresh]);

  const displayed = useMemo(() => data?.shortlist.slice(0, 20) ?? [], [data]);

  function toggleOpen() {
    if (!open) void refresh();
    setOpen((value) => !value);
  }

  return (
    <>
      <Button type="button" onClick={toggleOpen} className="fixed bottom-5 right-5 z-50 shadow-xl" aria-expanded={open}>
        <Radar className="size-4" /> Radar marché
        {data ? <Badge tone={statusTone(data.status)}>{data.status}</Badge> : null}
      </Button>

      {open ? (
        <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpen(false)} aria-hidden="true" />
      ) : null}

      {open ? (
        <Card className="fixed bottom-20 right-3 z-50 max-h-[78vh] w-[min(96vw,1080px)] overflow-hidden shadow-2xl sm:right-5">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="flex items-center gap-2"><Radar className="size-4" /> Market Attention</CardTitle>
                  <Badge tone="info">INFORMATIF — N’INFLUENCE PAS LE TRADING</Badge>
                  {data ? <Badge tone={statusTone(data.status)}>{data.status}</Badge> : null}
                </div>
                <CardDescription className="mt-1">Volume relatif Kraken + attention publique sourcée. Aucun BUY/SELL/HOLD, aucun signal de direction.</CardDescription>
              </div>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading} aria-label="Actualiser le radar">
                  <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setOpen(false)} aria-label="Fermer le radar"><X className="size-3.5" /></Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="max-h-[calc(78vh-110px)] overflow-y-auto py-4">
            {error ? <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground">{error}</div> : null}
            {data ? (
              <div className="space-y-4">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                  <Fact label="Catalogue" value={String(data.catalogue_market_count)} />
                  <Fact label="Activité en cache" value={String(data.cached_activity_market_count)} />
                  <Fact label="Scannés refresh" value={String(data.scanned_market_count)} />
                  <Fact label="Candidats" value={String(data.candidate_market_count)} />
                  <Fact label="Recherches web" value={String(data.web_search_count)} />
                </div>
                {displayed.length ? (
                  <div className="space-y-2">
                    {displayed.map((item) => {
                      const key = `${item.market_activity.market.market_type}:${item.market_activity.market.symbol}`;
                      return <MarketRow key={key} item={item} expanded={expandedKey === key} onToggle={() => setExpandedKey((value) => value === key ? null : key)} />;
                    })}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">
                    {loading ? "Construction du premier snapshot du radar…" : data.status === "NOT_CONFIGURED" ? "Radar non configuré." : "Aucun candidat d’attention disponible pour le moment."}
                  </div>
                )}
                <p className="text-[10px] text-muted-foreground">Snapshot {shortTime(data.observed_at)} · le classement porte uniquement sur le caractère inhabituel/convergent de l’attention.</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">{loading ? "Chargement du radar…" : "Aucun snapshot chargé."}</p>}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
