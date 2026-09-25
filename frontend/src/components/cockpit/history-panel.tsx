"use client";

import {
  Activity,
  Bot,
  CheckCircle2,
  Database,
  Radar,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCockpit } from "@/hooks/use-cockpit";
import { api, ApiError } from "@/lib/api/client";
import { formatDecimal, formatFailure, formatTimestamp, shortUuid } from "@/lib/api/format";
import type {
  CycleDetailResponse,
  CycleExplainabilityResponse,
  CycleSummaryResponse,
} from "@/lib/api/types";

function actionTone(action: string | null | undefined) {
  if (action === "BUY") return "success" as const;
  if (action === "SELL") return "danger" as const;
  return "neutral" as const;
}

function riskTone(status: string | null | undefined) {
  if (status === "ALLOW") return "success" as const;
  if (status === "MODIFY") return "warning" as const;
  if (status === "REJECT") return "danger" as const;
  return "neutral" as const;
}

function discoveryTone(status: string | null | undefined) {
  if (status === "REFRESHED") return "success" as const;
  if (status === "FALLBACK") return "warning" as const;
  if (status === "SKIPPED_MANAGEMENT") return "info" as const;
  return "neutral" as const;
}

function codeLabel(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—";
}

function discoveryDescription(explanation: CycleExplainabilityResponse | null) {
  const discovery = explanation?.discovery;
  if (!discovery) return "Discovery non disponible pour cet historique.";
  if (discovery.status === "REFRESHED") {
    return "Nouvelle watchlist sélectionnée par le même Agent IA à partir des candidats admis.";
  }
  if (discovery.status === "CACHE_REUSED") {
    return "Watchlist réutilisée : aucun nouvel appel IA de sélection n’a été effectué.";
  }
  if (discovery.status === "FALLBACK") {
    return "Refresh en échec : la dernière watchlist valide ou le bootstrap a été conservé.";
  }
  if (discovery.status === "SKIPPED_MANAGEMENT") {
    return "Discovery volontairement non lancée : le cycle était en mode MANAGEMENT.";
  }
  return `Statut discovery persistant : ${discovery.status}.`;
}

function executionDescription(explanation: CycleExplainabilityResponse | null) {
  const execution = explanation?.execution;
  if (!execution) return "Explicabilité d’exécution indisponible pour cet historique.";
  if (execution.outcome === "FILLED") {
    return `Exécution PAPER réelle : ${execution.fill_count} fill(s) persisté(s).`;
  }
  if (execution.outcome === "INTENT_CREATED_NO_FILL") {
    return "ExecutionIntent créé par Risk, mais aucun fill PAPER n’est persisté.";
  }
  if (execution.outcome === "NOT_CREATED_HOLD") {
    return "HOLD : l’absence d’exécution est le comportement métier attendu.";
  }
  if (execution.outcome === "NOT_CREATED_RISK_REJECT") {
    return "Risk a rejeté la proposition : aucun ExecutionIntent n’a été créé.";
  }
  if (execution.outcome === "NOT_CREATED_FAILURE") {
    return "Le cycle a échoué avant la création d’un ExecutionIntent.";
  }
  return "Aucun ExecutionIntent n’est persisté pour ce cycle.";
}

type DetailState =
  | { kind: "loading" }
  | { kind: "ready"; data: CycleDetailResponse }
  | { kind: "error"; message: string };

function CycleHistoryCard({ cycle }: { cycle: CycleSummaryResponse }) {
  const [detail, setDetail] = useState<DetailState>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    void api
      .cycle(cycle.cycle_id)
      .then((data) => {
        if (active) setDetail({ kind: "ready", data });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setDetail({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Détail du cycle indisponible",
        });
      });
    return () => {
      active = false;
    };
  }, [cycle.cycle_id]);

  const cycleDetail = detail.kind === "ready" ? detail.data : null;
  const explanation = cycleDetail?.explainability ?? null;
  const context = explanation?.context ?? null;
  const discovery = explanation?.discovery ?? null;
  const selection = explanation?.market_selection ?? null;
  const agent = explanation?.agent ?? null;
  const risk = explanation?.risk ?? null;
  const execution = explanation?.execution ?? null;
  const firstFill = execution?.fills[0] ?? null;

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">{agent?.symbol ?? cycle.symbol ?? "Cycle sans marché"}</CardTitle>
              {cycle.market_type ? (
                <Badge tone={cycle.market_type === "PERPETUAL" ? "warning" : "info"}>{cycle.market_type}</Badge>
              ) : null}
              <Badge tone={cycle.status === "FAILED" ? "danger" : "neutral"}>{cycle.status}</Badge>
              {context?.mode ? <Badge tone={context.mode === "MANAGEMENT" ? "warning" : "info"}>{context.mode}</Badge> : null}
            </div>
            <CardDescription className="mt-1">
              {formatTimestamp(cycle.recorded_at)} · cycle {shortUuid(cycle.cycle_id)}
            </CardDescription>
          </div>
          <span className="text-xs text-muted-foreground">{cycle.fill_count} fill(s)</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {detail.kind === "error" ? (
          <div className="rounded-lg border border-warning/30 bg-warning-subtle px-3 py-2 text-xs text-warning-foreground">
            {detail.message}. Le résumé du cycle reste visible, mais aucune explication n’est inventée.
          </div>
        ) : null}

        <div className="grid gap-3 xl:grid-cols-4">
          <div className="rounded-xl border bg-muted/15 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
              <Radar className="size-3.5" /> 1 · Discovery / contexte
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {discovery ? <Badge tone={discoveryTone(discovery.status)}>{discovery.status}</Badge> : <Badge>Legacy / —</Badge>}
              {context?.mode ? <Badge tone={context.mode === "MANAGEMENT" ? "warning" : "info"}>{context.mode}</Badge> : null}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {detail.kind === "loading" ? "Chargement des faits corrélés du cycle…" : discoveryDescription(explanation)}
            </p>
            {context?.reason ? (
              <p className="mt-2 text-[11px] text-muted-foreground">Capacité : <code>{codeLabel(context.reason)}</code></p>
            ) : null}
            {discovery?.selection_rationale ? (
              <div className="mt-3 rounded-lg border bg-background/70 p-3 text-xs">
                <p className="font-semibold">Pourquoi cette watchlist ?</p>
                <p className="mt-1 leading-relaxed text-muted-foreground">{discovery.selection_rationale}</p>
              </div>
            ) : null}
            {discovery?.selection_entries.length ? (
              <div className="mt-2 space-y-1.5 text-[11px] text-muted-foreground">
                {discovery.selection_entries.slice(0, 3).map((entry) => (
                  <p key={`${entry.market.market_type ?? "?"}-${entry.market.symbol}`}>
                    <strong className="text-foreground">{entry.market.symbol}</strong> · {entry.rationale ?? "Rationale non disponible"}
                  </p>
                ))}
              </div>
            ) : null}
            {selection ? (
              <div className="mt-3 rounded-lg border bg-background/70 p-3 text-xs">
                <p className="font-semibold">Pourquoi ce marché pour ce cycle ?</p>
                <p className="mt-1 leading-relaxed text-muted-foreground">
                  {selection.rationale ?? "Rationale non disponible pour cet historique"}
                </p>
              </div>
            ) : null}
            {discovery?.error_type ? (
              <p className="mt-2 text-[11px] text-warning-foreground">Erreur discovery : {discovery.error_type}</p>
            ) : null}
          </div>

          <div className="rounded-xl border bg-muted/15 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
              <Bot className="size-3.5" /> 2 · Agent IA
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {agent ? <Badge tone={actionTone(agent.action)}>{agent.action}</Badge> : <Badge>—</Badge>}
              <span className="text-sm font-medium">{agent?.symbol ?? cycle.symbol ?? "—"}</span>
            </div>
            <p className="mt-3 text-xs font-semibold">Pourquoi BUY / SELL / HOLD ?</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {agent?.rationale ?? "Rationale non disponible pour cet historique"}
            </p>
            {agent?.proposed_quantity ? (
              <p className="mt-3 text-xs">Quantité proposée : <strong>{formatDecimal(agent.proposed_quantity)}</strong></p>
            ) : agent?.action === "HOLD" ? (
              <p className="mt-3 text-xs text-muted-foreground">HOLD ne propose aucune quantité d’exécution.</p>
            ) : null}
          </div>

          <div className="rounded-xl border bg-muted/15 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
              <ShieldCheck className="size-3.5" /> 3 · Risk Engine
            </div>
            <div className="mt-3">{risk ? <Badge tone={riskTone(risk.status)}>Risk {risk.status}</Badge> : <Badge>Risk —</Badge>}</div>
            {agent?.action === "HOLD" && risk?.status === "ALLOW" ? (
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                HOLD autorisé : Risk confirme qu’aucune exécution n’est nécessaire.
              </p>
            ) : risk ? (
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                Résultat déterministe {risk.status}. Les raisons ci-dessous sont les codes canoniques persistés.
              </p>
            ) : (
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">Aucun résultat Risk persisté pour ce cycle.</p>
            )}
            {risk?.requested_quantity ? (
              <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                <div className="rounded-lg border bg-background/70 p-2.5">
                  <span className="text-muted-foreground">Demandée</span>
                  <strong className="mt-1 block">{formatDecimal(risk.requested_quantity)}</strong>
                </div>
                <div className="rounded-lg border bg-background/70 p-2.5">
                  <span className="text-muted-foreground">Autorisée</span>
                  <strong className="mt-1 block">{risk.authorized_quantity ? formatDecimal(risk.authorized_quantity) : "—"}</strong>
                </div>
              </div>
            ) : null}
            {risk?.reasons.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {risk.reasons.map((reason) => <Badge key={reason} tone={risk.status === "REJECT" ? "danger" : "warning"}>{codeLabel(reason)}</Badge>)}
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border bg-muted/15 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
              <Database className="size-3.5" /> 4 · Exécution PAPER
            </div>
            <div className="mt-3 flex items-center gap-2">
              {execution?.outcome === "FILLED" ? (
                <Badge tone="success"><CheckCircle2 className="mr-1 size-3" /> Exécuté</Badge>
              ) : (
                <Badge tone="neutral"><XCircle className="mr-1 size-3" /> Non exécuté</Badge>
              )}
              {execution ? <span className="text-xs text-muted-foreground">{execution.fill_count} fill(s)</span> : null}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{executionDescription(explanation)}</p>
            {execution?.quantity ? (
              <p className="mt-3 text-xs">Quantité intent : <strong>{formatDecimal(execution.quantity)}</strong></p>
            ) : null}
            {firstFill ? (
              <div className="mt-3 rounded-lg border bg-background/70 p-3 text-xs">
                <p className="font-semibold">Fill PAPER réel</p>
                <p className="mt-1 text-muted-foreground">
                  {firstFill.quantity ? `${formatDecimal(firstFill.quantity)} ` : ""}
                  {firstFill.symbol ?? agent?.symbol ?? ""}
                  {firstFill.price ? ` @ ${formatDecimal(firstFill.price)}` : ""}
                </p>
                {firstFill.fee ? <p className="mt-1 text-[11px] text-muted-foreground">Frais : {formatDecimal(firstFill.fee)}</p> : null}
              </div>
            ) : null}
          </div>
        </div>

        {(cycleDetail?.failure ?? cycle.failure) ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive-subtle px-3 py-2 text-xs text-destructive-subtle-foreground">
            Échec technique distinct de Risk : {formatFailure(cycleDetail?.failure ?? cycle.failure!)}
          </div>
        ) : null}

        {cycleDetail ? (
          <details className="rounded-lg border bg-muted/15 px-3 py-2 text-xs">
            <summary className="cursor-pointer rounded font-semibold">Détails techniques canoniques</summary>
            <div className="mt-3 grid gap-3 xl:grid-cols-2">
              <pre className="overflow-auto whitespace-pre-wrap rounded-lg border bg-background p-3 font-mono text-[10px] leading-relaxed text-foreground">
                {JSON.stringify({
                  market_selection_input: cycleDetail.market_selection_input,
                  market_selection: cycleDetail.market_selection,
                  decision: cycleDetail.decision,
                }, null, 2)}
              </pre>
              <pre className="overflow-auto whitespace-pre-wrap rounded-lg border bg-background p-3 font-mono text-[10px] leading-relaxed text-foreground">
                {JSON.stringify({
                  risk_assessment: cycleDetail.risk_assessment,
                  execution_intent: cycleDetail.execution_intent,
                  fills: cycleDetail.fills,
                  correlation: explanation?.correlation ?? null,
                }, null, 2)}
              </pre>
            </div>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function HistoryPanel() {
  const cockpit = useCockpit();
  const cycles = cockpit.resources.cycles.kind === "ready" ? cockpit.resources.cycles.data.items : [];
  const latestError = cockpit.resources.latestError.kind === "ready" ? cockpit.resources.latestError.data : null;

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Journal PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Historique</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Chaque cycle est relu depuis son détail corrélé : Discovery / contexte → Agent IA → Risk Engine → exécution PAPER.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void cockpit.refresh()} disabled={cockpit.refreshing}>
          <RefreshCw className={cockpit.refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      {latestError ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive-subtle-foreground">
          <p className="font-semibold">Dernière erreur technique</p>
          <p className="mt-1 text-xs">{formatFailure(latestError.failure)} · {formatTimestamp(latestError.recorded_at)}</p>
        </div>
      ) : null}

      <div className="space-y-4">
        {cycles.length ? cycles.map((cycle) => <CycleHistoryCard key={cycle.cycle_id} cycle={cycle} />) : (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
              <Activity className="size-6" />
              <p className="text-sm font-medium text-foreground">Aucun cycle journalisé</p>
              <p className="max-w-md text-xs">Démarre un test ou utilise « Tester 1 cycle » pour voir apparaître le parcours explicable complet.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
