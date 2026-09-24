"use client";

import { Activity, Bot, Database, RefreshCw, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCockpit } from "@/hooks/use-cockpit";
import { formatFailure, formatTimestamp, shortUuid } from "@/lib/api/format";

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

export function HistoryPanel() {
  const cockpit = useCockpit();
  const cycles = cockpit.resources.cycles.kind === "ready" ? cockpit.resources.cycles.data.items : [];
  const decisions = cockpit.resources.decisions.kind === "ready" ? cockpit.resources.decisions.data.items : [];
  const risks = cockpit.resources.riskAssessments.kind === "ready" ? cockpit.resources.riskAssessments.data.items : [];
  const executions = cockpit.resources.executions.kind === "ready" ? cockpit.resources.executions.data.items : [];
  const latestError = cockpit.resources.latestError.kind === "ready" ? cockpit.resources.latestError.data : null;

  const decisionsByCycle = new Map(decisions.map((item) => [item.cycle_id, item]));
  const risksByCycle = new Map(risks.map((item) => [item.cycle_id, item]));
  const executionsByCycle = new Map(executions.map((item) => [item.cycle_id, item]));

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Journal PAPER</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Historique</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Chaque cycle est présenté comme un parcours lisible : décision IA → contrôle Risk → éventuelle exécution PAPER.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void cockpit.refresh()} disabled={cockpit.refreshing}>
          <RefreshCw className={cockpit.refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      {latestError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-semibold">Dernière erreur technique</p>
          <p className="mt-1 text-xs">{formatFailure(latestError.failure)} · {formatTimestamp(latestError.recorded_at)}</p>
        </div>
      ) : null}

      <div className="space-y-4">
        {cycles.length ? cycles.map((cycle) => {
          const decision = decisionsByCycle.get(cycle.cycle_id);
          const risk = risksByCycle.get(cycle.cycle_id);
          const execution = executionsByCycle.get(cycle.cycle_id);
          return (
            <Card key={cycle.cycle_id} className="shadow-none">
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-base">{cycle.symbol ?? "Cycle sans marché"}</CardTitle>
                      {cycle.market_type ? <Badge tone={cycle.market_type === "PERPETUAL" ? "warning" : "info"}>{cycle.market_type}</Badge> : null}
                      <Badge tone={cycle.status === "FAILED" ? "danger" : "neutral"}>{cycle.status}</Badge>
                    </div>
                    <CardDescription className="mt-1">{formatTimestamp(cycle.recorded_at)} · cycle {shortUuid(cycle.cycle_id)}</CardDescription>
                  </div>
                  <span className="text-xs text-muted-foreground">{cycle.fill_count} fill(s)</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:items-stretch">
                  <div className="rounded-xl border p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><Bot className="size-3.5" /> 1 · Agent IA</div>
                    <div className="mt-3 flex items-center gap-2">{decision ? <Badge tone={actionTone(decision.action)}>{decision.action}</Badge> : <Badge>—</Badge>}<span className="text-sm font-medium">{decision?.symbol ?? cycle.symbol ?? "—"}</span></div>
                    <p className="mt-2 text-xs text-muted-foreground">{decision ? "Décision stratégique journalisée." : "Aucune décision persistée pour ce cycle."}</p>
                  </div>
                  <div className="hidden items-center text-muted-foreground lg:flex">→</div>
                  <div className="rounded-xl border p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><ShieldCheck className="size-3.5" /> 2 · Risk</div>
                    <div className="mt-3">{risk ? <Badge tone={riskTone(risk.status)}>{risk.status}</Badge> : <Badge>—</Badge>}</div>
                    <p className="mt-2 text-xs text-muted-foreground">{decision?.action === "HOLD" ? "HOLD : aucune exécution n’est attendue." : risk ? "Décision déterministe du Risk Engine." : "Aucun résultat Risk persisté."}</p>
                  </div>
                  <div className="hidden items-center text-muted-foreground lg:flex">→</div>
                  <div className="rounded-xl border p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><Database className="size-3.5" /> 3 · PAPER</div>
                    <div className="mt-3 flex items-center gap-2">{execution ? <Badge tone={actionTone(execution.action)}>{execution.action}</Badge> : <Badge>Pas d’exécution</Badge>}<span className="text-xs text-muted-foreground">{execution ? `${execution.fills.length} fill(s)` : ""}</span></div>
                    <p className="mt-2 text-xs text-muted-foreground">{execution ? "Intent autorisé/modifié puis traité par le Broker PAPER." : "Aucun intent Broker pour ce cycle."}</p>
                  </div>
                </div>

                {cycle.failure ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">{formatFailure(cycle.failure)}</div> : null}

                <details className="rounded-lg border bg-muted/15 px-3 py-2 text-xs">
                  <summary className="cursor-pointer font-semibold">Détails techniques</summary>
                  <div className="mt-3 grid gap-3 lg:grid-cols-3">
                    <pre className="overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 font-mono text-[10px] leading-relaxed">{JSON.stringify(decision?.payload ?? null, null, 2)}</pre>
                    <pre className="overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 font-mono text-[10px] leading-relaxed">{JSON.stringify(risk?.payload ?? null, null, 2)}</pre>
                    <pre className="overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 font-mono text-[10px] leading-relaxed">{JSON.stringify(execution?.payload ?? null, null, 2)}</pre>
                  </div>
                </details>
              </CardContent>
            </Card>
          );
        }) : (
          <Card className="border-dashed shadow-none"><CardContent className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground"><Activity className="size-6" /><p className="text-sm font-medium text-foreground">Aucun cycle journalisé</p><p className="max-w-md text-xs">Démarre un test ou utilise « Tester 1 cycle » pour voir apparaître le pipeline Agent → Risk → PAPER.</p></CardContent></Card>
        )}
      </div>
    </div>
  );
}
