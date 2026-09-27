"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type AuditRecord = {
  audit_id: string;
  recorded_at: string;
  sequence: number;
  category: "MARKET_DISCOVERY" | "STRATEGIC_MULTI_MARKET_PLAN" | "STRATEGIC_SINGLETON" | "OPERATOR_CHAT" | "UNKNOWN";
  model: string;
  session_id: string | null;
  cycle_id: string | null;
  discovery_id: string | null;
  request: Record<string, unknown>;
  response_output: Record<string, unknown>[];
  response_text: string | null;
};

type AuditPage = {
  items: AuditRecord[];
  retention_max_records: number;
  retention_max_record_bytes: number;
  persistence: "PROCESS_MEMORY";
};

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function short(value: string | null) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

export function LlmAuditPanel() {
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/backend/api/v1/llm-audit?limit=100", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setData((await response.json()) as AuditPage);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Audit LLM indisponible");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Lecture seule</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Inspecteur LLM</h2>
          <p className="mt-1 max-w-4xl text-sm leading-relaxed text-muted-foreground">
            Payloads réellement transmis à OpenAI Responses API. Aucun preview reconstruit, aucun contrôle de trading.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rétention</CardTitle>
          <CardDescription>
            {data ? `${data.retention_max_records} appels maximum · ${Math.round(data.retention_max_record_bytes / 1024)} Kio maximum par appel · mémoire processus` : "Chargement…"}
          </CardDescription>
        </CardHeader>
        {error ? <CardContent className="text-sm text-destructive">{error}</CardContent> : null}
      </Card>

      <div className="space-y-4">
        {data?.items.map((item) => {
          const request = item.request;
          const format = (request.text as { format?: unknown } | undefined)?.format ?? null;
          return (
            <Card key={item.audit_id}>
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="info">#{item.sequence}</Badge>
                  <Badge tone="neutral">{item.category}</Badge>
                  <span className="font-semibold">{item.model}</span>
                  <span className="text-xs text-muted-foreground">{new Date(item.recorded_at).toLocaleString("fr-FR")}</span>
                </div>
                <CardDescription>
                  cycle {short(item.cycle_id)} · session {short(item.session_id)} · discovery {short(item.discovery_id)}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <section><h3 className="mb-2 text-sm font-semibold">instructions exactes</h3><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border bg-muted/20 p-3 text-xs">{String(request.instructions ?? "")}</pre></section>
                <section><h3 className="mb-2 text-sm font-semibold">input exact</h3><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border bg-muted/20 p-3 text-xs">{pretty(request.input ?? null)}</pre></section>
                <section><h3 className="mb-2 text-sm font-semibold">JSON Schema / format</h3><pre className="max-h-96 overflow-auto rounded-xl border bg-muted/20 p-3 text-xs">{pretty(format)}</pre></section>
                <section><h3 className="mb-2 text-sm font-semibold">tools exposés</h3><pre className="max-h-96 overflow-auto rounded-xl border bg-muted/20 p-3 text-xs">{pretty(request.tools ?? [])}</pre></section>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border bg-muted/20 p-3 text-xs"><strong>parallel_tool_calls</strong><div className="mt-1">{String(request.parallel_tool_calls ?? "non transmis")}</div></div>
                  <div className="rounded-xl border bg-muted/20 p-3 text-xs"><strong>store</strong><div className="mt-1">{String(request.store ?? "non transmis")}</div></div>
                </div>
                <section><h3 className="mb-2 text-sm font-semibold">output fournisseur</h3><pre className="max-h-[32rem] overflow-auto rounded-xl border bg-muted/20 p-3 text-xs">{pretty(item.response_output)}</pre></section>
                <section><h3 className="mb-2 text-sm font-semibold">réponse textuelle / structurée finale</h3><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border bg-muted/20 p-3 text-xs">{item.response_text ?? "Aucun output_text sur cet appel (ex. étape tool intermédiaire)."}</pre></section>
              </CardContent>
            </Card>
          );
        })}
        {data && data.items.length === 0 ? <Card><CardContent className="py-8 text-sm text-muted-foreground">Aucun appel LLM capturé depuis le démarrage du backend.</CardContent></Card> : null}
      </div>
    </div>
  );
}
