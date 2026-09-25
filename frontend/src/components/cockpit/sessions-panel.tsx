"use client";

import {
  Activity,
  Archive,
  Bot,
  Copy,
  FolderOpen,
  PauseCircle,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Square,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ControlPlaneController } from "@/hooks/use-control-plane";
import { formatTimestamp } from "@/lib/api/format";
import type { SessionResponse, SessionStatus } from "@/lib/api/types";
import { sessionStatusLabel } from "@/lib/session-config";

function statusTone(status: SessionStatus): "success" | "info" | "warning" | "neutral" {
  if (status === "RUNNING") return "success";
  if (status === "READY") return "info";
  if (status === "RESUMABLE") return "warning";
  return "neutral";
}

function sessionSummary(session: SessionResponse) {
  const configuration = session.configuration;
  const model = configuration.llm_model === "gpt-5.6-sol" ? "Sol" : "Luna";
  const mode = session.market_mode === "AUTOMATIC_AI"
    ? "Auto IA"
    : `Manuel · ${configuration.paper_executable_markets.length} marché${configuration.paper_executable_markets.length > 1 ? "s" : ""}`;
  return `${configuration.paper_initial_capital} ${configuration.paper_settlement_asset} · ${model} · ${mode} · Agressivité ${configuration.aggressiveness}`;
}

function PrimaryLifecycleAction({ session, control }: { session: SessionResponse; control: ControlPlaneController }) {
  const busy = control.busyAction !== null;
  if (session.status === "RUNNING") {
    return (
      <Button variant="destructive" size="sm" onClick={() => void control.stopSession(session.session_id)} disabled={busy}>
        <Square className="size-3.5" /> Arrêter
      </Button>
    );
  }
  if (session.status === "READY") {
    return (
      <Button size="sm" onClick={() => void control.startSession(session.session_id)} disabled={busy}>
        <Play className="size-3.5" /> Démarrer
      </Button>
    );
  }
  if (session.current_campaign_has_history) {
    return (
      <Button size="sm" onClick={() => void control.resumeSession(session.session_id)} disabled={busy}>
        <RotateCcw className="size-3.5" /> Reprendre
      </Button>
    );
  }
  return (
    <Button size="sm" onClick={() => void control.startSession(session.session_id)} disabled={busy}>
      <Play className="size-3.5" /> Démarrer
    </Button>
  );
}

export function SessionsPanel({
  control,
  onCreate,
  onEdit,
}: {
  control: ControlPlaneController;
  onCreate: () => void;
  onEdit: (session: SessionResponse) => void;
}) {
  const [openSessionId, setOpenSessionId] = useState<string | null>(null);
  const busy = control.busyAction !== null;

  async function archive(session: SessionResponse) {
    if (!window.confirm(`Supprimer « ${session.name} » de la liste des Sessions ? L’historique d’audit sera conservé.`)) return;
    await control.archiveSession(session.session_id);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Pilotage PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Sessions</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Crée, configure, démarre, arrête et reprends tes Sessions sans manipuler les objets techniques internes.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void control.refresh()} disabled={control.refreshing}>
            <RefreshCw className={control.refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
          </Button>
          <Button onClick={onCreate}><Plus className="size-4" /> Nouvelle session</Button>
        </div>
      </div>

      {control.feedback ? (
        <div className={control.feedback.tone === "error"
          ? "rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive-subtle-foreground"
          : "rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-200"}>
          {control.feedback.message}
        </div>
      ) : null}

      {control.loading ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Chargement des Sessions…</CardContent></Card>
      ) : control.sessions.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-4 py-14 text-center">
            <div className="rounded-2xl border bg-muted/30 p-4"><Bot className="size-7" /></div>
            <div>
              <p className="font-semibold">Aucune Session</p>
              <p className="mt-1 max-w-lg text-sm text-muted-foreground">Commence par une configuration simple ; les paramètres avancés restent disponibles dans le même formulaire.</p>
            </div>
            <Button onClick={onCreate}><Plus className="size-4" /> Nouvelle session</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {control.sessions.map((session) => {
            const open = openSessionId === session.session_id;
            return (
              <Card key={session.session_id} className="overflow-hidden">
                <CardHeader className="gap-3 pb-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="truncate text-lg">{session.name}</CardTitle>
                        <Badge tone={statusTone(session.status)}>{sessionStatusLabel(session.status)}</Badge>
                        <Badge tone="neutral">{session.configuration.paper_executable_markets[0]?.market_type ?? "PAPER"}</Badge>
                      </div>
                      <CardDescription className="mt-1">{sessionSummary(session)}</CardDescription>
                      <p className="mt-2 text-xs text-muted-foreground">Dernière activité {formatTimestamp(session.last_activity_at)}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => setOpenSessionId(open ? null : session.session_id)}>
                        <FolderOpen className="size-3.5" /> {open ? "Fermer" : "Ouvrir"}
                      </Button>
                      <PrimaryLifecycleAction session={session} control={control} />
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="border-t pt-4">
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => onEdit(session)} disabled={busy || session.status === "RUNNING"}>
                      <Pencil className="size-3.5" /> Modifier
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => void control.duplicateSession(session.session_id)} disabled={busy}>
                      <Copy className="size-3.5" /> Dupliquer
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => void control.runSessionCycle(session.session_id)} disabled={busy || session.status === "RUNNING"}>
                      <Activity className="size-3.5" /> Tester 1 cycle
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => void archive(session)} disabled={busy || session.status === "RUNNING"}>
                      <Archive className="size-3.5" /> Supprimer
                    </Button>
                  </div>

                  {open ? (
                    <div className="mt-5 grid gap-4 border-t pt-5 md:grid-cols-2 xl:grid-cols-3">
                      <div className="rounded-xl border bg-muted/15 p-4">
                        <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><Bot className="size-3.5" /> IA</p>
                        <p className="mt-2 text-sm font-semibold">{session.configuration.llm_model === "gpt-5.6-sol" ? "Sol" : "Luna"} · agressivité {session.configuration.aggressiveness}/10</p>
                        <p className="mt-2 line-clamp-4 text-xs leading-relaxed text-muted-foreground">{session.instructions}</p>
                      </div>
                      <div className="rounded-xl border bg-muted/15 p-4">
                        <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><PauseCircle className="size-3.5" /> Marchés</p>
                        <p className="mt-2 text-sm font-semibold">{session.market_mode === "AUTOMATIC_AI" ? "Automatique — IA" : "Manuel"}</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {session.configuration.paper_executable_markets.map((market) => <Badge key={`${market.market_type}:${market.symbol}`} tone="neutral">{market.symbol}</Badge>)}
                        </div>
                        {session.market_mode === "AUTOMATIC_AI" ? <p className="mt-2 text-xs text-muted-foreground">Ces marchés sont le bootstrap/fallback ; la watchlist effective peut être découverte dynamiquement.</p> : null}
                      </div>
                      <div className="rounded-xl border bg-muted/15 p-4">
                        <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><ShieldCheck className="size-3.5" /> Historique</p>
                        <p className="mt-2 text-sm font-semibold">{session.has_history ? "Historique conservé" : "Jamais exécutée"}</p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {session.latest_paper_run
                            ? `Dernière exécution ${session.latest_paper_run.ended_at ? `arrêtée ${formatTimestamp(session.latest_paper_run.ended_at)}` : "à reprendre explicitement"}.`
                            : "Aucune exécution PAPER pour cette Session."}
                        </p>
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
