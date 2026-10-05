"use client";

import { BrainCircuit, History, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDecimal, formatTimestamp, shortUuid } from "@/lib/api/format";
import {
  fetchStrategicTheses,
  revisionsForStrategicPosition,
  strategicThesisPositionKey,
  type StrategicThesisObservabilityResponse,
  type StrategicThesisPositionResponse,
  type StrategicThesisRevisionResponse,
  type StrategicThesisStatus,
} from "@/lib/strategic-theses";

type ThesisState =
  | { kind: "idle" }
  | { kind: "ready"; paperRunId: string; data: StrategicThesisObservabilityResponse }
  | { kind: "error"; paperRunId: string; message: string };

function statusTone(status: StrategicThesisStatus | null) {
  if (status === "CONFIRMED") return "success" as const;
  if (status === "WEAKENING") return "warning" as const;
  if (status === "INVALIDATED") return "danger" as const;
  if (status === "COMPLETED") return "info" as const;
  return "neutral" as const;
}

function revisionStateLabel(item: StrategicThesisRevisionResponse): string {
  const labels: Record<StrategicThesisRevisionResponse["revision_state"], string> = {
    ACTIVE_COMMITTED: "thèse active commitée",
    RETIRED_COMMITTED: "thèse retirée après cycle",
    PROPOSED_NOT_ACTIVATED: "proposition non activée",
    FAILED_CYCLE: "cycle FAILED — non promu",
    UNAVAILABLE_LEGACY: "état durable indisponible",
  };
  return labels[item.revision_state];
}

function FactList({ values, empty }: { values: string[]; empty: string }) {
  if (values.length === 0) return <p className="text-xs text-muted-foreground">{empty}</p>;
  return (
    <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
      {values.map((item) => <li key={item}>• {item}</li>)}
    </ul>
  );
}

function RevisionRows({ revisions }: { revisions: StrategicThesisRevisionResponse[] }) {
  if (revisions.length === 0) return null;
  return (
    <div className="space-y-2 border-t pt-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Révisions durables</p>
      {revisions.slice(-6).reverse().map((item) => (
        <div key={`${item.cycle_id}-${item.decision_index}`} className="rounded-lg border bg-muted/10 p-3 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={statusTone(item.status)}>{item.status}</Badge>
            <Badge>{item.agent_action}</Badge>
            {item.risk_status ? <Badge>Risk {item.risk_status}</Badge> : null}
            <span className="text-muted-foreground">{formatTimestamp(item.reviewed_at)}</span>
          </div>
          <p className="mt-2 leading-relaxed">{item.review_summary}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {revisionStateLabel(item)} · {item.fill_count} fill(s) · cycle {shortUuid(item.cycle_id)}
          </p>
        </div>
      ))}
    </div>
  );
}

function ThesisCard({
  item,
  report,
}: {
  item: StrategicThesisPositionResponse;
  report: StrategicThesisObservabilityResponse;
}) {
  if (item.memory_state === "UNAVAILABLE_LEGACY") {
    return (
      <Card className="border-dashed">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{item.symbol}</CardTitle>
            <Badge tone={item.market_type === "PERPETUAL" ? "warning" : "info"}>{item.market_type}</Badge>
            <Badge>{item.side}</Badge>
          </div>
          <CardDescription>Quantité {formatDecimal(item.quantity)}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm font-medium">Historique stratégique indisponible</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Position ouverte avant activation de la mémoire 50.1, ou sans thèse durable disponible. Aucune ancienne rationale n’a été reconstruite.
          </p>
        </CardContent>
      </Card>
    );
  }

  const revisions = revisionsForStrategicPosition(report, item);
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{item.symbol}</CardTitle>
            <Badge tone={item.market_type === "PERPETUAL" ? "warning" : "info"}>{item.market_type}</Badge>
            <Badge>{item.side}</Badge>
            <Badge tone={statusTone(item.status)}>{item.status ?? "—"}</Badge>
          </div>
          <span className="font-mono text-xs text-muted-foreground">{formatDecimal(item.quantity)}</span>
        </div>
        <CardDescription>
          {item.origin === "LEGACY_ADOPTION" ? "Thèse adoptée sur position legacy" : "Thèse créée à l’ouverture économique"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div><span className="text-muted-foreground">Horizon</span><p className="font-medium">{item.horizon ?? "—"}</p></div>
          <div><span className="text-muted-foreground">Créée</span><p>{formatTimestamp(item.created_at)}</p></div>
          <div><span className="text-muted-foreground">Activée</span><p>{formatTimestamp(item.activated_at)}</p></div>
          <div><span className="text-muted-foreground">Dernière revue</span><p>{formatTimestamp(item.last_review?.reviewed_at ?? item.updated_at)}</p></div>
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Thèse</p>
          <p className="mt-1 text-sm leading-relaxed">{item.thesis_summary ?? "—"}</p>
          {item.last_review ? <p className="mt-2 text-xs text-muted-foreground">Dernière revue : {item.last_review.summary}</p> : null}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Faits de support</p>
            <FactList values={item.supporting_facts} empty="Aucun fait de support structuré." />
          </div>
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Conditions d’invalidation</p>
            <FactList values={item.invalidation_conditions} empty="Aucune condition d’invalidation structurée." />
          </div>
        </div>
        <RevisionRows revisions={revisions} />
      </CardContent>
    </Card>
  );
}

function GlobalRevisionHistory({ report }: { report: StrategicThesisObservabilityResponse }) {
  if (report.revisions.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base"><History className="size-4" /> Historique causal des révisions</CardTitle>
        <CardDescription>
          {report.revisions.length} révision(s) affichée(s) sur {report.total_revision_count}. Les propositions non activées et cycles FAILED restent distincts de l’état actif.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {report.revisions.slice(-12).reverse().map((item) => (
          <div key={`${item.cycle_id}-${item.decision_index}`} className="grid gap-2 rounded-lg border p-3 text-xs lg:grid-cols-[180px_1fr_auto] lg:items-start">
            <div>
              <p className="font-semibold">{item.symbol}</p>
              <div className="mt-1 flex flex-wrap gap-1"><Badge>{item.market_type}</Badge>{item.side ? <Badge>{item.side}</Badge> : null}</div>
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                <Badge>{item.agent_action}</Badge>
                {item.risk_status ? <Badge>Risk {item.risk_status}</Badge> : null}
              </div>
              <p className="mt-2 leading-relaxed">{item.review_summary}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">{revisionStateLabel(item)} · {item.fill_count} fill(s)</p>
            </div>
            <div className="text-right text-[11px] text-muted-foreground">
              <p>{formatTimestamp(item.reviewed_at)}</p>
              <p className="mt-1 font-mono">{shortUuid(item.cycle_id)}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function StrategicThesisSection({
  paperRunId,
  refreshNonce,
}: {
  paperRunId: string | null;
  refreshNonce: number;
}) {
  const [state, setState] = useState<ThesisState>({ kind: "idle" });

  useEffect(() => {
    if (!paperRunId) return;
    let active = true;
    void fetchStrategicTheses(paperRunId)
      .then((data) => {
        if (active) setState({ kind: "ready", paperRunId, data });
      })
      .catch((error: unknown) => {
        if (active) {
          setState({
            kind: "error",
            paperRunId,
            message: error instanceof Error ? error.message : "Mémoire stratégique indisponible",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [paperRunId, refreshNonce]);

  if (!paperRunId) return null;
  const report = state.kind === "ready" && state.paperRunId === paperRunId ? state.data : null;
  const error = state.kind === "error" && state.paperRunId === paperRunId ? state.message : null;
  const loading = report === null && error === null;

  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Mémoire stratégique PAPER 50.2</p>
        <h3 className="mt-1 flex items-center gap-2 text-xl font-semibold"><BrainCircuit className="size-5" /> Continuité des thèses</h3>
        <p className="mt-1 max-w-4xl text-sm text-muted-foreground">
          Vue read-only des faits persistés par 50.1. Le cockpit n’invente aucune thèse et ne déclenche aucune action.
        </p>
      </div>

      <div className="flex gap-3 rounded-xl border bg-muted/15 p-4 text-xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" />
        <p>
          NEW, CONFIRMED, WEAKENING, INVALIDATED et COMPLETED qualifient la stratégie de l’Agent. INVALIDATED ou COMPLETED ne signifie pas « SELL », et WEAKENING n’impose pas une réduction. Le Risk Engine reste l’autorité finale sur toute exécution.
        </p>
      </div>

      {loading ? <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">Lecture de la mémoire stratégique durable…</CardContent></Card> : null}
      {error ? <div className="rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive-subtle-foreground">{error}</div> : null}

      {report ? (
        <>
          {report.positions.length === 0 ? (
            <Card className="border-dashed"><CardContent className="py-8 text-center text-sm text-muted-foreground">Aucune exposition PAPER ouverte à laquelle rattacher une thèse active.</CardContent></Card>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {report.positions.map((item) => (
                <ThesisCard key={strategicThesisPositionKey(item)} item={item} report={report} />
              ))}
            </div>
          )}
          <GlobalRevisionHistory report={report} />
          <p className="text-[11px] text-muted-foreground">
            Source {report.calculation_version} · lineage {report.lineage_paper_run_ids.length} run(s) · état {formatTimestamp(report.as_of)}.
          </p>
        </>
      ) : null}
    </section>
  );
}
