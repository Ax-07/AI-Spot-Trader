"use client";

import {
  Activity,
  ChevronDown,
  ChevronUp,
  Download,
  RefreshCw,
  ReceiptText,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api/client";
import { formatDecimal, formatFailure, formatTimestamp, shortUuid } from "@/lib/api/format";
import type {
  CampaignResponse,
  CycleDetailResponse,
  CycleSummaryResponse,
  PaperRunResponse,
  SessionResponse,
} from "@/lib/api/types";
import {
  economicHistoryExportPath,
  fetchEconomicHistory,
  paperObservabilityMarketKey,
  type EconomicHistoryResponse,
  type EconomicOperationResponse,
  type PaperMarketObservabilityResponse,
  type PaperObservabilityBreakdownResponse,
} from "@/lib/economic-history";

type ReferenceState =
  | { kind: "loading" }
  | {
      kind: "ready";
      sessions: SessionResponse[];
      campaigns: CampaignResponse[];
      runs: PaperRunResponse[];
    }
  | { kind: "error"; message: string };

type HistoryState =
  | { kind: "idle" }
  | { kind: "ready"; paperRunId: string; data: EconomicHistoryResponse }
  | { kind: "error"; paperRunId: string; message: string };

type DetailState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; data: CycleDetailResponse }
  | { kind: "error"; message: string };

function percent(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(parsed * 100)} %`;
}

function actionTone(action: string | null | undefined) {
  if (action === "BUY") return "success" as const;
  if (action === "SELL") return "danger" as const;
  return "neutral" as const;
}

function riskTone(value: string | null | undefined) {
  if (value === "ALLOW") return "success" as const;
  if (value === "MODIFY") return "warning" as const;
  if (value === "REJECT") return "danger" as const;
  return "neutral" as const;
}

function effectLabel(effect: string): string {
  const labels: Record<string, string> = {
    OPEN_SPOT: "Ouverture SPOT",
    INCREASE_SPOT: "Augmentation SPOT",
    REDUCE_SPOT: "Réduction SPOT",
    CLOSE_SPOT: "Clôture SPOT",
    OPEN_LONG: "Ouverture LONG",
    INCREASE_LONG: "Augmentation LONG",
    REDUCE_LONG: "Réduction LONG",
    CLOSE_LONG: "Clôture LONG",
    OPEN_SHORT: "Ouverture SHORT",
    INCREASE_SHORT: "Augmentation SHORT",
    REDUCE_SHORT: "Réduction SHORT",
    CLOSE_SHORT: "Clôture SHORT",
    FLIP_LONG_TO_SHORT: "LONG → SHORT",
    FLIP_SHORT_TO_LONG: "SHORT → LONG",
    EXECUTED_LONG: "Exécution LONG",
    EXECUTED_SHORT: "Exécution SHORT",
    EXECUTED_SPOT: "Exécution SPOT",
    EXECUTED_FLAT: "Exécution à plat",
  };
  return labels[effect] ?? effect.replaceAll("_", " ");
}

function positionLabel(value: string, marketType: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  if (marketType === "SPOT") return formatDecimal(value);
  if (parsed > 0) return `LONG ${formatDecimal(value)}`;
  if (parsed < 0) return `SHORT ${formatDecimal(Math.abs(parsed))}`;
  return "FLAT";
}

async function loadAllPaperRuns(): Promise<PaperRunResponse[]> {
  const result: PaperRunResponse[] = [];
  let offset = 0;
  while (true) {
    const page = await api.paperRuns(100, offset);
    result.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) break;
  }
  return result;
}

function sessionRunHeads(
  sessionId: string | null,
  campaigns: CampaignResponse[],
  runs: PaperRunResponse[],
): PaperRunResponse[] {
  if (!sessionId) return [];
  const campaignIds = new Set(
    campaigns.filter((item) => item.strategy_id === sessionId).map((item) => item.campaign_id),
  );
  const sessionRuns = runs.filter((item) => item.campaign_id && campaignIds.has(item.campaign_id));
  const resumedParents = new Set(
    sessionRuns
      .map((item) => item.resumed_from_paper_run_id)
      .filter((item): item is string => Boolean(item)),
  );
  return sessionRuns
    .filter((item) => !resumedParents.has(item.paper_run_id))
    .sort((left, right) => right.started_at.localeCompare(left.started_at));
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border bg-muted/15 p-4">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight">{value}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
    </div>
  );
}

function BreakdownCard({ item }: { item: PaperObservabilityBreakdownResponse }) {
  const net = item.net_pnl === null ? "—" : formatDecimal(item.net_pnl);
  const gross = item.gross_pnl === null ? "indisponible" : formatDecimal(item.gross_pnl);
  return (
    <Card className="gap-3 py-5">
      <CardHeader className="px-5 pb-0">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{item.scope}</CardTitle>
          <Badge tone={item.scope === "PERPETUAL" ? "warning" : item.scope === "SPOT" ? "info" : "neutral"}>
            {item.trade_count} trade(s)
          </Badge>
        </div>
        <CardDescription>
          {item.scope === "TOTAL" ? "Source économique canonique" : "Attribution uniquement lorsque les faits le permettent"}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 px-5 text-xs sm:grid-cols-2">
        <div><span className="text-muted-foreground">P&L net</span><p className="font-mono text-sm">{net}</p></div>
        <div><span className="text-muted-foreground">P&L brut</span><p className="font-mono text-sm">{gross}</p></div>
        <div><span className="text-muted-foreground">Réalisé</span><p className="font-mono text-sm">{formatDecimal(item.realized_pnl)}</p></div>
        <div><span className="text-muted-foreground">Latent</span><p className="font-mono text-sm">{formatDecimal(item.unrealized_pnl)}</p></div>
        <div><span className="text-muted-foreground">Coûts économiques</span><p className="font-mono text-sm">{formatDecimal(item.total_costs)}</p></div>
        <div><span className="text-muted-foreground">Funding</span><p className="font-mono text-sm">{formatDecimal(item.funding_pnl)}</p></div>
        <div><span className="text-muted-foreground">Exposition</span><p className="font-mono text-sm">{formatDecimal(item.current_exposure_value)}</p></div>
        <div><span className="text-muted-foreground">Exposition / equity</span><p className="text-sm">{percent(item.current_exposure_fraction)}</p></div>
      </CardContent>
    </Card>
  );
}

function MarketObservabilityTable({ markets }: { markets: PaperMarketObservabilityResponse[] }) {
  if (markets.length === 0) {
    return <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Aucun marché observé.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="min-w-[1150px] w-full text-xs">
        <thead className="bg-muted/50 text-left text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Marché</th>
            <th className="px-3 py-2 font-medium">Agent</th>
            <th className="px-3 py-2 font-medium">Risk</th>
            <th className="px-3 py-2 font-medium">Exécution</th>
            <th className="px-3 py-2 text-right font-medium">Montant</th>
            <th className="px-3 py-2 text-right font-medium">Coûts</th>
            <th className="px-3 py-2 text-right font-medium">Funding</th>
            <th className="px-3 py-2 text-right font-medium">P&L réalisé</th>
            <th className="px-3 py-2 text-right font-medium">Exposition</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {markets.map((item) => (
            <tr key={paperObservabilityMarketKey(item)}>
              <td className="px-3 py-3"><span className="font-semibold">{item.symbol}</span> <Badge>{item.market_type}</Badge></td>
              <td className="px-3 py-3">{item.decision_count} · B {item.buy_count} / S {item.sell_count} / H {item.hold_count}</td>
              <td className="px-3 py-3">A {item.risk_allow_count} / M {item.risk_modify_count} / R {item.risk_reject_count}</td>
              <td className="px-3 py-3">{item.decisions_with_fill} décision(s) fillée(s) · {item.fill_count} fill(s) · {item.trade_count} trade(s)</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.total_notional)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.total_costs)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.funding_pnl)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.realized_pnl)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.current_exposure_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ObservabilitySection({ report }: { report: EconomicHistoryResponse }) {
  const observability = report.observability;
  if (!observability) return null;
  const funnel = observability.funnel;
  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Observabilité PAPER 49.4</p>
        <h3 className="mt-1 text-xl font-semibold">TOTAL / SPOT / PERPETUAL</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Les valeurs absentes restent indisponibles : aucun P&L brut/net par type n’est réparti artificiellement.
        </p>
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        {observability.breakdowns.map((item) => <BreakdownCard key={item.scope} item={item} />)}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="size-4" /> Funnel Agent → Risk → exécution</CardTitle>
          <CardDescription>Une décision n’est jamais assimilée à un trade ou à un fill.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Agent" value={String(funnel.decision_count)} detail={`BUY ${funnel.buy_count} · SELL ${funnel.sell_count} · HOLD ${funnel.hold_count}`} />
          <MetricCard label="Risk" value={`ALLOW ${funnel.risk_allow_count}`} detail={`MODIFY ${funnel.risk_modify_count} · REJECT ${funnel.risk_reject_count}`} />
          <MetricCard label="Décisions fillées" value={String(funnel.decisions_with_fill)} detail={`${funnel.decisions_without_fill} sans fill · ${funnel.execution_intent_count} intent(s)`} />
          <MetricCard label="Économie" value={`${funnel.economic_trade_count} trade(s)`} detail={`${funnel.fill_count} fill(s) économiquement engagés`} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Ventilation par marché</CardTitle>
          <CardDescription>Identité stricte (symbol, market_type) : SPOT et PERPETUAL restent séparés.</CardDescription>
        </CardHeader>
        <CardContent>
          <MarketObservabilityTable markets={observability.markets} />
        </CardContent>
      </Card>
      {observability.unavailable_metrics.length ? (
        <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
          Métriques volontairement non attribuées : {observability.unavailable_metrics.join(" · ")}
        </p>
      ) : null}
    </section>
  );
}

function AuditCycleCard({ cycle }: { cycle: CycleSummaryResponse }) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<DetailState>({ kind: "idle" });

  function toggleDetails() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (detail.kind !== "idle") return;
    setDetail({ kind: "loading" });
    void api
      .cycle(cycle.cycle_id)
      .then((data) => setDetail({ kind: "ready", data }))
      .catch((error: unknown) => {
        setDetail({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Détail du cycle indisponible",
        });
      });
  }

  const decisions = detail.kind === "ready" ? detail.data.explainability?.decisions ?? [] : [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">Cycle {shortUuid(cycle.cycle_id)}</CardTitle>
              <Badge tone={cycle.status === "FAILED" ? "danger" : "neutral"}>{cycle.status}</Badge>
              {cycle.market_type ? <Badge tone={cycle.market_type === "PERPETUAL" ? "warning" : "info"}>{cycle.market_type}</Badge> : null}
            </div>
            <CardDescription className="mt-1">{formatTimestamp(cycle.recorded_at)}</CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={toggleDetails}>
            {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            {expanded ? "Masquer" : "Détails"}
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5 pt-1 text-[11px]">
          <Badge>{cycle.decision_count} décision(s)</Badge>
          {cycle.buy_count ? <Badge tone="success">{cycle.buy_count} BUY</Badge> : null}
          {cycle.sell_count ? <Badge tone="danger">{cycle.sell_count} SELL</Badge> : null}
          {cycle.hold_count ? <Badge>{cycle.hold_count} HOLD</Badge> : null}
          {cycle.risk_reject_count ? <Badge tone="warning">{cycle.risk_reject_count} REJECT</Badge> : null}
          {cycle.fill_count ? <Badge tone="info">{cycle.fill_count} fill(s)</Badge> : null}
        </div>
      </CardHeader>

      {expanded ? (
        <CardContent className="space-y-3 border-t pt-4">
          {detail.kind === "loading" ? <p className="text-sm text-muted-foreground">Chargement du détail canonique…</p> : null}
          {detail.kind === "error" ? <p className="text-sm text-destructive">{detail.message}</p> : null}
          {detail.kind === "ready" && decisions.length === 0 ? (
            <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
              Aucune décision explicable persistée pour ce cycle.
            </p>
          ) : null}
          {decisions.map((item) => (
            <div key={`${cycle.cycle_id}-${item.decision_index}`} className="rounded-lg border bg-muted/10 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Décision {item.decision_index + 1}</span>
                <Badge tone={actionTone(item.agent.action)}>{item.agent.action}</Badge>
                <span className="text-sm font-semibold">{item.agent.symbol}</span>
                {item.agent.market_type ? <Badge>{item.agent.market_type}</Badge> : null}
                {item.risk ? <Badge tone={riskTone(item.risk.status)}>Risk {item.risk.status}</Badge> : null}
                <Badge tone={item.execution.outcome === "FILLED" ? "success" : "neutral"}>{item.execution.outcome}</Badge>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {item.agent.rationale ?? "Rationale non disponible pour cet historique."}
              </p>
              {item.risk?.reasons.length ? (
                <p className="mt-2 text-[11px] text-muted-foreground">Risk : {item.risk.reasons.join(" · ")}</p>
              ) : null}
            </div>
          ))}
          {detail.kind === "ready" && detail.data.failure ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground">
              {formatFailure(detail.data.failure)}
            </div>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}

function OperationsTable({ operations }: { operations: EconomicOperationResponse[] }) {
  if (operations.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
        Aucune opération économique ne correspond aux filtres.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="min-w-[1500px] w-full text-sm">
        <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Horodatage</th>
            <th className="px-3 py-2 font-medium">Cycle / ordre</th>
            <th className="px-3 py-2 font-medium">Marché</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Effet économique</th>
            <th className="px-3 py-2 text-right font-medium">Quantité</th>
            <th className="px-3 py-2 text-right font-medium">Prix</th>
            <th className="px-3 py-2 text-right font-medium">Montant de l’ordre</th>
            <th className="px-3 py-2 text-right font-medium">Coûts</th>
            <th className="px-3 py-2 text-right font-medium">P&L réalisé</th>
            <th className="px-3 py-2 font-medium">Position avant → après</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {operations.map((item) => (
            <tr key={item.execution_id} className="align-top">
              <td className="px-3 py-3 whitespace-nowrap">{formatTimestamp(item.filled_at)}</td>
              <td className="px-3 py-3">
                <div className="font-mono text-xs">{shortUuid(item.cycle_id)}</div>
                <div className="mt-1 text-[11px] text-muted-foreground">décision {item.decision_index + 1} · {item.fill_count} fill(s)</div>
              </td>
              <td className="px-3 py-3">
                <div className="font-semibold">{item.symbol}</div>
                <Badge tone={item.market_type === "PERPETUAL" ? "warning" : "info"}>{item.market_type}</Badge>
              </td>
              <td className="px-3 py-3"><Badge tone={actionTone(item.action)}>{item.action}</Badge></td>
              <td className="px-3 py-3 font-medium">{effectLabel(item.economic_effect)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.quantity)}</td>
              <td className="px-3 py-3 text-right font-mono">
                {formatDecimal(item.price)}
                <div className="text-[10px] text-muted-foreground">ref. {formatDecimal(item.reference_price)}</div>
              </td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.notional)}</td>
              <td className="px-3 py-3 text-right font-mono">
                {formatDecimal(item.total_costs)}
                <div className="text-[10px] text-muted-foreground">
                  fee {formatDecimal(item.fee)} · spread {formatDecimal(item.spread_cost)} · slip {formatDecimal(item.slippage_cost)}
                </div>
                {Number(item.funding_pnl) !== 0 ? <div className="text-[10px] text-muted-foreground">funding {formatDecimal(item.funding_pnl)}</div> : null}
              </td>
              <td className="px-3 py-3 text-right font-mono">{formatDecimal(item.realized_pnl)}</td>
              <td className="px-3 py-3 text-xs">
                {positionLabel(item.position_before, item.market_type)} → {positionLabel(item.position_after, item.market_type)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HistoryPanel() {
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [reference, setReference] = useState<ReferenceState>({ kind: "loading" });
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryState>({ kind: "idle" });
  const [actionFilter, setActionFilter] = useState<"ALL" | "BUY" | "SELL">("ALL");
  const [marketTypeFilter, setMarketTypeFilter] = useState<"ALL" | "SPOT" | "PERPETUAL">("ALL");
  const [symbolFilter, setSymbolFilter] = useState("ALL");

  useEffect(() => {
    let active = true;
    void Promise.all([api.sessions(), api.campaigns(), loadAllPaperRuns()])
      .then(([sessions, campaigns, runs]) => {
        if (!active) return;
        setReference({ kind: "ready", sessions, campaigns, runs });
        setSelectedSessionId((current) => {
          if (current && sessions.some((item) => item.session_id === current)) return current;
          return sessions.find((item) => item.status === "RUNNING")?.session_id ?? sessions[0]?.session_id ?? null;
        });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setReference({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Historique des Sessions indisponible",
        });
      });
    return () => {
      active = false;
    };
  }, [refreshNonce]);

  const runHeads = useMemo(() => {
    if (reference.kind !== "ready") return [];
    return sessionRunHeads(selectedSessionId, reference.campaigns, reference.runs);
  }, [reference, selectedSessionId]);
  const effectiveRunId =
    selectedRunId && runHeads.some((item) => item.paper_run_id === selectedRunId)
      ? selectedRunId
      : runHeads[0]?.paper_run_id ?? null;

  useEffect(() => {
    if (!effectiveRunId) return;
    let active = true;
    void fetchEconomicHistory(effectiveRunId)
      .then((data) => {
        if (active) setHistory({ kind: "ready", paperRunId: effectiveRunId, data });
      })
      .catch((error: unknown) => {
        if (active) {
          setHistory({
            kind: "error",
            paperRunId: effectiveRunId,
            message: error instanceof Error ? error.message : "Historique économique indisponible",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [effectiveRunId, refreshNonce]);

  const report = history.kind === "ready" && history.paperRunId === effectiveRunId ? history.data : null;
  const historyError = history.kind === "error" && history.paperRunId === effectiveRunId ? history.message : null;
  const historyLoading = Boolean(effectiveRunId) && report === null && historyError === null;
  const symbols = useMemo(
    () => [...new Set(report?.operations.map((item) => item.symbol) ?? [])].sort(),
    [report],
  );
  const filteredOperations = useMemo(() => {
    if (!report) return [];
    return report.operations.filter((item) => {
      if (actionFilter !== "ALL" && item.action !== actionFilter) return false;
      if (marketTypeFilter !== "ALL" && item.market_type !== marketTypeFilter) return false;
      if (symbolFilter !== "ALL" && item.symbol !== symbolFilter) return false;
      return true;
    });
  }, [actionFilter, marketTypeFilter, report, symbolFilter]);

  const summary = report?.summary ?? null;

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Historique économique PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Historique</h2>
          <p className="mt-1 max-w-4xl text-sm leading-relaxed text-muted-foreground">
            Session → run économique → opérations réellement exécutées. Les P&L, coûts, positions et métriques proviennent du backend canonique ; le cockpit ne les recalcule pas.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setReference({ kind: "loading" });
            setHistory({ kind: "idle" });
            setRefreshNonce((value) => value + 1);
          }}
          disabled={reference.kind === "loading" || historyLoading}
        >
          <RefreshCw className={reference.kind === "loading" || historyLoading ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <Card>
        <CardContent className="grid gap-4 py-5 lg:grid-cols-2">
          <label className="space-y-1.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Session</span>
            <select
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={selectedSessionId ?? ""}
              onChange={(event) => {
                setActionFilter("ALL");
                setMarketTypeFilter("ALL");
                setSymbolFilter("ALL");
                setHistory({ kind: "idle" });
                setSelectedRunId(null);
                setSelectedSessionId(event.target.value || null);
              }}
              disabled={reference.kind !== "ready"}
            >
              {reference.kind === "ready" && reference.sessions.length === 0 ? <option value="">Aucune Session</option> : null}
              {reference.kind === "ready" ? reference.sessions.map((session) => (
                <option key={session.session_id} value={session.session_id}>{session.name} · {session.status}</option>
              )) : <option value="">Chargement…</option>}
            </select>
          </label>
          <label className="space-y-1.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Run économique / Campaign</span>
            <select
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={effectiveRunId ?? ""}
              onChange={(event) => {
                setActionFilter("ALL");
                setMarketTypeFilter("ALL");
                setSymbolFilter("ALL");
                setHistory({ kind: "idle" });
                setSelectedRunId(event.target.value || null);
              }}
              disabled={runHeads.length === 0}
            >
              {runHeads.length === 0 ? <option value="">Aucun run PAPER pour cette Session</option> : runHeads.map((run) => (
                <option key={run.paper_run_id} value={run.paper_run_id}>
                  {formatTimestamp(run.started_at)} · {run.ended_at ? "terminé" : "actif / reprenable"} · {shortUuid(run.paper_run_id)}
                </option>
              ))}
            </select>
          </label>
        </CardContent>
      </Card>

      {reference.kind === "error" ? <div className="rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive-subtle-foreground">{reference.message}</div> : null}
      {historyError ? <div className="rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive-subtle-foreground">{historyError}</div> : null}
      {historyLoading ? <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Reconstruction de l’historique économique depuis les faits persistés…</CardContent></Card> : null}

      {summary && report ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
            <MetricCard label="Equity" value={`${formatDecimal(summary.initial_equity)} → ${formatDecimal(summary.ending_equity)}`} detail="Initiale → finale / actuelle" />
            <MetricCard label="P&L net" value={formatDecimal(summary.net_pnl)} detail={`Brut ${formatDecimal(summary.gross_pnl)}`} />
            <MetricCard label="P&L réalisé" value={formatDecimal(summary.realized_pnl)} detail={`Latent ${formatDecimal(summary.unrealized_pnl)}`} />
            <MetricCard label="Coûts totaux" value={formatDecimal(summary.total_costs)} detail={`Exécution ${formatDecimal(summary.execution_costs)} · funding ${formatDecimal(summary.funding_pnl)}`} />
            <MetricCard label="Drawdown max" value={percent(summary.max_drawdown_fraction)} detail={`Actuel ${percent(summary.current_drawdown_fraction)} · ${formatDecimal(summary.max_drawdown_value)} max`} />
            <MetricCard label="Exposition" value={percent(summary.current_exposure_fraction)} detail={`${formatDecimal(summary.current_exposure_value)} à la dernière valorisation durable`} />
            <MetricCard label="Turnover" value={percent(summary.turnover_fraction)} detail={`Montant échangé ${formatDecimal(summary.total_notional)} / equity initiale`} />
            <MetricCard label="Cadence réelle" value={summary.fills_per_hour === null ? "—" : `${formatDecimal(summary.fills_per_hour)} fills/h`} detail={`${summary.trade_count} trade(s) · ${summary.fill_count} fill(s)`} />
          </section>

          <ObservabilitySection report={report} />

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><ReceiptText className="size-4" /> Coûts & rotation</CardTitle>
                <CardDescription>Ratios descriptifs, sans score stratégique.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <MetricCard label="Frais" value={formatDecimal(summary.fees)} detail="Fills PAPER" />
                <MetricCard label="Spread" value={formatDecimal(summary.spread_cost)} detail="Coût d’exécution" />
                <MetricCard label="Slippage" value={formatDecimal(summary.slippage_cost)} detail="Coût d’exécution" />
                <MetricCard label="Coûts / montant échangé" value={percent(summary.costs_to_notional_fraction)} detail="Coûts totaux / montant échangé" />
                <MetricCard label="Coûts / equity" value={percent(summary.costs_to_initial_equity_fraction)} detail="Coûts totaux / equity initiale" />
                <MetricCard label="Changements de marché" value={String(summary.market_switch_count)} detail={summary.market_switches_per_hour === null ? "cadence indisponible" : `${formatDecimal(summary.market_switches_per_hour)} / h`} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="size-4" /> Décisions & effets</CardTitle>
                <CardDescription>HOLD et REJECT restent de l’audit ; ils ne deviennent pas des trades.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <MetricCard label="Décisions" value={String(summary.decision_count)} detail={`BUY ${summary.buy_decision_count} · SELL ${summary.sell_decision_count}`} />
                <MetricCard label="Sans exécution" value={`HOLD ${summary.hold_count}`} detail={`REJECT ${summary.reject_count} · MODIFY ${summary.modify_count}`} />
                <MetricCard label="Ouvertures" value={String(summary.open_count)} detail={`augmentations ${summary.increase_count}`} />
                <MetricCard label="Réductions" value={String(summary.reduce_count)} detail={`clôtures ${summary.close_count} · flips ${summary.flip_count}`} />
                <MetricCard label="Effets LONG" value={String(summary.long_effect_count)} detail="Opérations PERPETUAL liées au LONG" />
                <MetricCard label="Effets SHORT" value={String(summary.short_effect_count)} detail="Opérations PERPETUAL liées au SHORT" />
              </CardContent>
            </Card>
          </section>

          <Card>
            <CardHeader className="gap-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <CardTitle>Opérations économiques</CardTitle>
                  <CardDescription>
                    Une ligne par exécution économique ; plusieurs fills d’un même ExecutionIntent sont agrégés sans reconstruire le P&L côté frontend.
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={() => { window.location.href = economicHistoryExportPath(report.paper_run_id); }}>
                  <Download className="size-3.5" /> Exporter JSON
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <select className="h-9 rounded-md border bg-background px-3 text-xs" value={actionFilter} onChange={(event) => setActionFilter(event.target.value as "ALL" | "BUY" | "SELL")}>
                  <option value="ALL">Toutes les actions</option><option value="BUY">BUY</option><option value="SELL">SELL</option>
                </select>
                <select className="h-9 rounded-md border bg-background px-3 text-xs" value={marketTypeFilter} onChange={(event) => setMarketTypeFilter(event.target.value as "ALL" | "SPOT" | "PERPETUAL")}>
                  <option value="ALL">Tous les types</option><option value="SPOT">SPOT</option><option value="PERPETUAL">PERPETUAL</option>
                </select>
                <select className="h-9 rounded-md border bg-background px-3 text-xs" value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)}>
                  <option value="ALL">Tous les marchés</option>
                  {symbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
                </select>
              </div>
            </CardHeader>
            <CardContent>
              <OperationsTable operations={filteredOperations} />
              <p className="mt-3 text-xs text-muted-foreground">{filteredOperations.length} opération(s) affichée(s) sur {report.operations.length}. Source {report.calculation_version} · digest {report.source_digest.slice(0, 12)}…</p>
            </CardContent>
          </Card>

          <section className="space-y-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Audit Agent → Risk → PAPER</p>
              <h3 className="mt-1 text-xl font-semibold">Décisions récentes du run</h3>
              <p className="mt-1 text-sm text-muted-foreground">Les HOLD, REJECT et échecs restent consultables séparément des opérations économiques.</p>
            </div>
            {report.cycles.length ? report.cycles.slice(0, 12).map((cycle) => <AuditCycleCard key={cycle.cycle_id} cycle={cycle} />) : (
              <Card className="border-dashed"><CardContent className="flex flex-col items-center gap-2 py-10 text-center text-muted-foreground"><Activity className="size-5" /><p className="text-sm">Aucun cycle journalisé pour ce run.</p></CardContent></Card>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
