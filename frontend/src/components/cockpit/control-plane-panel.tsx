"use client";

import {
  Activity,
  Archive,
  Bot,
  Database,
  Eye,
  GitCompare,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import {
  type FormEvent,
  type ReactNode,
  useMemo,
  useState,
} from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useControlPlane } from "@/hooks/use-control-plane";
import { formatTimestamp, shortUuid } from "@/lib/api/format";
import type {
  CampaignConfiguration,
  ExecutableMarketResponse,
  LlmModel,
  PromptPreviewPhase,
  PromptPreviewResponse,
  StrategyRevisionComparisonResponse,
} from "@/lib/api/types";

const inputClass =
  "h-10 w-full rounded-md border bg-background px-3 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";
const textareaClass =
  "min-h-32 w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";
const selectClass = inputClass;

const CONTROL_CONFIGURATION_VERSION = "paper-control-plane-config-v1";

type CampaignDraft = {
  llmModel: LlmModel;
  aggressiveness: string;
  cadenceSeconds: string;
  initialCapital: string;
  settlementAsset: string;
  markets: ExecutableMarketResponse[];
  feeRate: string;
  spreadBps: string;
  slippageBps: string;
  derivativeLeverage: string;
  riskMaxOrderNotional: string;
  riskAllowedPairs: string;
  riskAllowQuantityReduction: boolean;
  riskMaxDerivativeLeverage: string;
  riskMaxDerivativePositionNotional: string;
  riskMaxTotalDerivativeExposure: string;
  liquidationBufferRatio: string;
  marketTimeoutSeconds: string;
  agentTimeoutSeconds: string;
  brokerTimeoutSeconds: string;
};

const DEFAULT_CAMPAIGN: CampaignDraft = {
  llmModel: "gpt-5.6-luna",
  aggressiveness: "5",
  cadenceSeconds: "30",
  initialCapital: "1000",
  settlementAsset: "USD",
  markets: [{ symbol: "BTC/USD", market_type: "SPOT" }],
  feeRate: "0.001",
  spreadBps: "2",
  slippageBps: "2",
  derivativeLeverage: "1",
  riskMaxOrderNotional: "100",
  riskAllowedPairs: "BTC/USD",
  riskAllowQuantityReduction: true,
  riskMaxDerivativeLeverage: "1",
  riskMaxDerivativePositionNotional: "",
  riskMaxTotalDerivativeExposure: "",
  liquidationBufferRatio: "1.10",
  marketTimeoutSeconds: "20",
  agentTimeoutSeconds: "35",
  brokerTimeoutSeconds: "5",
};

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint ? <span className="text-xs leading-relaxed text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

function Digest({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="font-mono text-[11px]" title={value}>
      {value.slice(0, 12)}…{value.slice(-8)}
    </span>
  );
}

function parseNumber(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error("Valeur numérique invalide");
  return parsed;
}

function nullableDecimal(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function riskPairs(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function promptSections(preview: PromptPreviewResponse | null) {
  if (!preview) return null;
  const strategyMarker = "\n\nSTRATEGIE OPERATEUR EDITABLE (subordonnee au contrat protege) :\n";
  const aggressivenessMarker = "\n\nCONTEXTE D'AGRESSIVITE CANONIQUE :\n";
  const strategyIndex = preview.instructions.indexOf(strategyMarker);
  const aggressivenessIndex = preview.instructions.indexOf(aggressivenessMarker);
  if (strategyIndex < 0 || aggressivenessIndex < 0 || aggressivenessIndex <= strategyIndex) {
    return {
      protectedContract: preview.instructions,
      operatorStrategy: "Section non isolable : affichage canonique complet ci-dessus.",
      aggressiveness: "Section non isolable.",
    };
  }
  return {
    protectedContract: preview.instructions.slice(0, strategyIndex),
    operatorStrategy: preview.instructions.slice(
      strategyIndex + strategyMarker.length,
      aggressivenessIndex,
    ),
    aggressiveness: preview.instructions.slice(aggressivenessIndex + aggressivenessMarker.length),
  };
}

function campaignConfiguration(draft: CampaignDraft): CampaignConfiguration {
  return {
    configuration_version: CONTROL_CONFIGURATION_VERSION,
    llm_model: draft.llmModel,
    aggressiveness: parseNumber(draft.aggressiveness),
    trading_cadence_seconds: parseNumber(draft.cadenceSeconds),
    paper_initial_capital: draft.initialCapital.trim(),
    paper_settlement_asset: draft.settlementAsset.trim(),
    paper_executable_markets: draft.markets.map((market) => ({
      symbol: market.symbol.trim(),
      market_type: market.market_type,
    })),
    paper_fee_rate: draft.feeRate.trim(),
    paper_spread_bps: draft.spreadBps.trim(),
    paper_slippage_bps: draft.slippageBps.trim(),
    paper_derivative_leverage: draft.derivativeLeverage.trim(),
    paper_derivative_margin_mode: "ISOLATED",
    risk_max_order_notional: draft.riskMaxOrderNotional.trim(),
    risk_allowed_pairs: riskPairs(draft.riskAllowedPairs),
    risk_allow_quantity_reduction: draft.riskAllowQuantityReduction,
    risk_max_derivative_leverage: draft.riskMaxDerivativeLeverage.trim(),
    risk_max_derivative_position_notional: nullableDecimal(
      draft.riskMaxDerivativePositionNotional,
    ),
    risk_max_total_derivative_exposure: nullableDecimal(
      draft.riskMaxTotalDerivativeExposure,
    ),
    risk_derivative_liquidation_buffer_ratio: draft.liquidationBufferRatio.trim(),
    cycle_market_timeout_seconds: parseNumber(draft.marketTimeoutSeconds),
    cycle_agent_timeout_seconds: parseNumber(draft.agentTimeoutSeconds),
    cycle_broker_timeout_seconds: parseNumber(draft.brokerTimeoutSeconds),
  };
}

export function ControlPlanePanel() {
  const control = useControlPlane();
  const [newStrategyName, setNewStrategyName] = useState("");
  const [newStrategyPrompt, setNewStrategyPrompt] = useState("");
  const strategyId = control.selectedStrategy?.strategy_id ?? null;
  const strategyName = control.selectedStrategy?.strategy_name ?? "";
  const latestRevisionNumber = control.selectedStrategy?.latest_revision ?? null;
  const strategyRevisionKey = strategyId ? `${strategyId}:${latestRevisionNumber ?? "none"}` : null;
  const renameKey = strategyId ? `${strategyId}:${strategyName}` : null;

  const [renameDraft, setRenameDraft] = useState<{ key: string; value: string } | null>(null);
  const [revisionSelection, setRevisionSelection] = useState<{ key: string; value: number } | null>(null);
  const [revisionDraft, setRevisionDraft] = useState<{ key: string; value: string } | null>(null);
  const [compareSelection, setCompareSelection] = useState<{
    key: string;
    left: number | null;
    right: number | null;
  } | null>(null);
  const [comparisonResult, setComparisonResult] = useState<{
    key: string;
    value: StrategyRevisionComparisonResponse;
  } | null>(null);
  const [previewPhase, setPreviewPhase] = useState<PromptPreviewPhase>("MARKET_SELECTION");
  const [previewAggressiveness, setPreviewAggressiveness] = useState("5");
  const [previewResult, setPreviewResult] = useState<{
    key: string;
    value: PromptPreviewResponse;
  } | null>(null);
  const [campaignDraft, setCampaignDraft] = useState<CampaignDraft>(DEFAULT_CAMPAIGN);
  const [localError, setLocalError] = useState<string | null>(null);

  const renameValue = renameKey && renameDraft?.key === renameKey ? renameDraft.value : strategyName;
  const selectedRevisionNumber =
    strategyRevisionKey && revisionSelection?.key === strategyRevisionKey
      ? revisionSelection.value
      : latestRevisionNumber;
  const defaultCompareRight = latestRevisionNumber;
  const defaultCompareLeft =
    latestRevisionNumber && latestRevisionNumber > 1 ? latestRevisionNumber - 1 : latestRevisionNumber;
  const compareLeft =
    strategyRevisionKey && compareSelection?.key === strategyRevisionKey
      ? compareSelection.left
      : defaultCompareLeft;
  const compareRight =
    strategyRevisionKey && compareSelection?.key === strategyRevisionKey
      ? compareSelection.right
      : defaultCompareRight;

  const selectedRevision = useMemo(
    () =>
      control.revisions.find((item) => item.strategy_revision === selectedRevisionNumber) ?? null,
    [control.revisions, selectedRevisionNumber],
  );
  const revisionKey = selectedRevision
    ? `${selectedRevision.strategy_id}:${selectedRevision.strategy_revision}:${selectedRevision.strategy_prompt_digest}`
    : null;
  const revisionPrompt =
    revisionKey && revisionDraft?.key === revisionKey
      ? revisionDraft.value
      : (selectedRevision?.strategy_prompt ?? "");
  const comparisonKey =
    strategyId && compareLeft !== null && compareRight !== null
      ? `${strategyId}:${compareLeft}:${compareRight}`
      : null;
  const comparison =
    comparisonKey && comparisonResult?.key === comparisonKey ? comparisonResult.value : null;
  const previewKey =
    strategyId && selectedRevisionNumber !== null
      ? `${strategyId}:${selectedRevisionNumber}:${previewPhase}:${previewAggressiveness}`
      : null;
  const preview = previewKey && previewResult?.key === previewKey ? previewResult.value : null;

  function setRenameValue(value: string) {
    if (renameKey) setRenameDraft({ key: renameKey, value });
  }

  function setSelectedRevisionNumber(value: number) {
    if (strategyRevisionKey) setRevisionSelection({ key: strategyRevisionKey, value });
  }

  function setRevisionPrompt(value: string) {
    if (revisionKey) setRevisionDraft({ key: revisionKey, value });
  }

  function setCompareLeft(value: number | null) {
    if (!strategyRevisionKey) return;
    setCompareSelection((current) => ({
      key: strategyRevisionKey,
      left: value,
      right: current?.key === strategyRevisionKey ? current.right : defaultCompareRight,
    }));
  }

  function setCompareRight(value: number | null) {
    if (!strategyRevisionKey) return;
    setCompareSelection((current) => ({
      key: strategyRevisionKey,
      left: current?.key === strategyRevisionKey ? current.left : defaultCompareLeft,
      right: value,
    }));
  }

  const previewParts = promptSections(preview);
  const hasPerpetual = campaignDraft.markets.some((market) => market.market_type === "PERPETUAL");
  const activeCampaign = control.activeCampaign?.campaign ?? null;
  const activePaperRun = control.activeCampaign?.paper_run_id
    ? control.paperRuns.items.find(
        (item) => item.paper_run_id === control.activeCampaign?.paper_run_id,
      ) ?? null
    : null;
  const engine = control.engine;
  const commandBusy = control.busyAction?.startsWith("engine-") ?? false;

  async function submitNewStrategy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    const result = await control.createStrategy(newStrategyName, newStrategyPrompt);
    if (result) {
      setNewStrategyName("");
      setNewStrategyPrompt("");
    }
  }

  async function submitRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!control.selectedStrategy) return;
    await control.renameStrategy(control.selectedStrategy.strategy_id, renameValue);
  }

  async function submitRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!control.selectedStrategy) return;
    await control.createRevision(control.selectedStrategy.strategy_id, revisionPrompt);
  }

  async function requestComparison() {
    if (!control.selectedStrategy || compareLeft === null || compareRight === null) return;
    const result = await control.compareRevisions(
      control.selectedStrategy.strategy_id,
      compareLeft,
      compareRight,
    );
    if (result && comparisonKey) setComparisonResult({ key: comparisonKey, value: result });
  }

  async function requestPreview() {
    if (!control.selectedStrategy || selectedRevisionNumber === null) return;
    setLocalError(null);
    try {
      const result = await control.previewPrompt(
        control.selectedStrategy.strategy_id,
        selectedRevisionNumber,
        parseNumber(previewAggressiveness),
        previewPhase,
      );
      if (result && previewKey) setPreviewResult({ key: previewKey, value: result });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Paramètre de preview invalide");
    }
  }

  async function submitCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!control.selectedStrategy || selectedRevisionNumber === null) return;
    setLocalError(null);
    try {
      const configuration = campaignConfiguration(campaignDraft);
      await control.createCampaign(
        control.selectedStrategy.strategy_id,
        selectedRevisionNumber,
        configuration,
      );
    } catch (error) {
      setLocalError(
        error instanceof Error ? error.message : "Configuration Campaign invalide côté navigateur",
      );
    }
  }

  function updateMarket(index: number, patch: Partial<ExecutableMarketResponse>) {
    setCampaignDraft((current) => ({
      ...current,
      markets: current.markets.map((market, marketIndex) =>
        marketIndex === index ? { ...market, ...patch } : market,
      ),
    }));
  }

  function removeMarket(index: number) {
    setCampaignDraft((current) => ({
      ...current,
      markets: current.markets.filter((_, marketIndex) => marketIndex !== index),
    }));
  }

  return (
    <section className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 pb-8 pt-2 sm:px-6 lg:px-8">
      <Card className="border-foreground/15">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-xl">Control Plane PAPER</CardTitle>
                <Badge tone="info">Batch 18.9B</Badge>
                <Badge>SPOT + PERPETUAL</Badge>
              </div>
              <CardDescription>
                Configuration, activation et pilotage du runtime backend canonique. Aucune décision
                de trading, règle Risk ou exécution Broker n’est implémentée dans ce panneau.
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">
                lecture {formatTimestamp(control.lastUpdatedAt)}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void control.refresh()}
                disabled={control.refreshing}
              >
                <RefreshCw className={control.refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
                Actualiser
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {(control.feedback || localError) && (
            <div
              className={`rounded-lg border p-3 text-sm ${
                control.feedback?.tone === "error" || localError
                  ? "border-red-200 bg-red-50 text-red-800"
                  : "border-emerald-200 bg-emerald-50 text-emerald-800"
              }`}
            >
              {localError ?? control.feedback?.message}
              {control.feedback?.status === 409 ? (
                <span className="ml-2 font-semibold">Conflit fail-closed backend.</span>
              ) : control.feedback?.status === 422 ? (
                <span className="ml-2 font-semibold">Validation refusée par le backend.</span>
              ) : control.feedback?.status === 503 ? (
                <span className="ml-2 font-semibold">Opération indisponible / fail-closed.</span>
              ) : null}
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border bg-muted/20 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Campaign active</p>
              <p className="mt-1 font-semibold">
                {activeCampaign ? shortUuid(activeCampaign.campaign_id) : "Aucune"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {activeCampaign
                  ? `Strategy r${activeCampaign.strategy_revision}`
                  : "Une activation est toujours explicite."}
              </p>
            </div>
            <div className="rounded-lg border bg-muted/20 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">paper_run</p>
              <p className="mt-1 font-mono text-sm">
                {shortUuid(control.activeCampaign?.paper_run_id)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                reprise depuis {shortUuid(activePaperRun?.resumed_from_paper_run_id)}
              </p>
            </div>
            <div className="rounded-lg border bg-muted/20 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Recovery</p>
              <p className="mt-1 font-semibold">{activePaperRun?.recovery_version ?? "—"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                lineage lu via /api/v1/paper-runs
              </p>
            </div>
            <div className="rounded-lg border bg-muted/20 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Moteur</p>
              <p className="mt-1 font-semibold">{engine?.status ?? "UNAVAILABLE"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {engine?.configured ? "runtime Campaign configuré" : "aucune Campaign active"}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
            <div className="mr-auto min-w-[240px]">
              <p className="font-medium">Commandes TradingEngine canoniques</p>
              <p className="text-xs text-muted-foreground">
                Run-cycle = exactement un cycle ; Start = boucle autonome backend ; Stop = arrêt
                explicite. Fermer ce frontend n’envoie jamais Stop.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => void control.runCycle()}
              disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
            >
              <Activity className="size-4" />
              Run cycle
            </Button>
            <Button
              onClick={() => void control.startEngine()}
              disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
            >
              <Play className="size-4" />
              Start
            </Button>
            <Button
              variant="destructive"
              onClick={() => void control.stopEngine()}
              disabled={!engine?.configured || engine.status !== "RUNNING" || commandBusy}
            >
              <Square className="size-4" />
              Stop
            </Button>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
        <Card>
          <CardHeader>
            <CardTitle>Strategies</CardTitle>
            <CardDescription>
              Strategy = identité mutable (nom/archive). Le texte vit uniquement dans des
              StrategyRevision immuables.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <form className="space-y-3 rounded-lg border p-4" onSubmit={submitNewStrategy}>
              <div className="flex items-center gap-2 font-medium">
                <Plus className="size-4" /> Créer une Strategy
              </div>
              <Field label="Nom">
                <input
                  className={inputClass}
                  value={newStrategyName}
                  onChange={(event) => setNewStrategyName(event.target.value)}
                  required
                  maxLength={120}
                  placeholder="Momentum discrétionnaire PAPER"
                />
              </Field>
              <Field
                label="Prompt stratégique — révision 1"
                hint="Le backend normalise le texte, refuse les motifs de secret et calcule le digest canonique."
              >
                <textarea
                  className={textareaClass}
                  value={newStrategyPrompt}
                  onChange={(event) => setNewStrategyPrompt(event.target.value)}
                  required
                  placeholder="Décris ici la stratégie de l'Agent, sans secret ni consigne visant à contourner Risk."
                />
              </Field>
              <Button type="submit" disabled={control.busyAction !== null}>
                <Plus className="size-4" /> Créer Strategy + r1
              </Button>
            </form>

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Strategies persistées
              </p>
              {control.loading ? (
                <p className="text-sm text-muted-foreground">Chargement…</p>
              ) : control.strategies.length ? (
                <div className="space-y-2">
                  {control.strategies.map((strategy) => {
                    const selected = strategy.strategy_id === control.selectedStrategyId;
                    return (
                      <button
                        key={strategy.strategy_id}
                        type="button"
                        onClick={() => control.setSelectedStrategyId(strategy.strategy_id)}
                        className={`w-full rounded-lg border p-3 text-left transition ${
                          selected ? "border-foreground/40 bg-muted/40" : "hover:bg-muted/25"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate font-medium">{strategy.strategy_name}</p>
                            <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                              {shortUuid(strategy.strategy_id)}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <Badge tone={strategy.archived_at ? "warning" : "success"}>
                              {strategy.archived_at ? "archivée" : "active"}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              r{strategy.latest_revision ?? "—"}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                  Aucune Strategy persistée.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle>StrategyRevision</CardTitle>
                <CardDescription>
                  Sélection, édition par nouvelle révision, comparaison et preview canonique.
                </CardDescription>
              </div>
              {control.selectedStrategy ? (
                <Badge tone={control.selectedStrategy.archived_at ? "warning" : "info"}>
                  {control.selectedStrategy.strategy_name}
                </Badge>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {!control.selectedStrategy ? (
              <p className="text-sm text-muted-foreground">Sélectionne ou crée une Strategy.</p>
            ) : (
              <>
                <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
                  <form className="flex gap-2" onSubmit={submitRename}>
                    <input
                      className={inputClass}
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      disabled={control.selectedStrategy.archived_at !== null}
                      maxLength={120}
                      required
                    />
                    <Button
                      type="submit"
                      variant="outline"
                      disabled={
                        control.selectedStrategy.archived_at !== null || control.busyAction !== null
                      }
                    >
                      <Pencil className="size-4" /> Renommer
                    </Button>
                  </form>
                  <Button
                    variant="outline"
                    onClick={() => void control.archiveStrategy(control.selectedStrategy!.strategy_id)}
                    disabled={
                      control.selectedStrategy.archived_at !== null || control.busyAction !== null
                    }
                  >
                    <Archive className="size-4" /> Archiver
                  </Button>
                </div>

                <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Révisions
                    </p>
                    {control.revisionsLoading ? (
                      <p className="text-sm text-muted-foreground">Chargement…</p>
                    ) : (
                      control.revisions.map((revision) => (
                        <button
                          key={revision.strategy_revision}
                          type="button"
                          onClick={() => setSelectedRevisionNumber(revision.strategy_revision)}
                          className={`w-full rounded-lg border p-3 text-left ${
                            revision.strategy_revision === selectedRevisionNumber
                              ? "border-foreground/40 bg-muted/40"
                              : "hover:bg-muted/25"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold">r{revision.strategy_revision}</span>
                            <span className="text-[11px] text-muted-foreground">
                              {formatTimestamp(revision.created_at)}
                            </span>
                          </div>
                          <div className="mt-2"><Digest value={revision.strategy_prompt_digest} /></div>
                        </button>
                      ))
                    )}
                  </div>

                  <form className="space-y-3" onSubmit={submitRevision}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-medium">
                          Éditeur basé sur r{selectedRevisionNumber ?? "—"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Enregistrer ne modifie jamais la révision sélectionnée : une nouvelle révision
                          est créée.
                        </p>
                      </div>
                      {selectedRevision ? (
                        <Badge>{selectedRevision.base_agent_contract_version}</Badge>
                      ) : null}
                    </div>
                    <textarea
                      className={`${textareaClass} min-h-56 font-mono text-xs leading-relaxed`}
                      value={revisionPrompt}
                      onChange={(event) => setRevisionPrompt(event.target.value)}
                      disabled={control.selectedStrategy.archived_at !== null}
                      required
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="submit"
                        disabled={
                          control.selectedStrategy.archived_at !== null || control.busyAction !== null
                        }
                      >
                        <Plus className="size-4" /> Créer une nouvelle révision
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setRevisionPrompt(selectedRevision?.strategy_prompt ?? "")}
                      >
                        <RotateCcw className="size-4" /> Réinitialiser l’éditeur
                      </Button>
                    </div>
                  </form>
                </div>

                <div className="grid gap-4 border-t pt-5 lg:grid-cols-2">
                  <div className="space-y-3 rounded-lg border p-4">
                    <div className="flex items-center gap-2 font-medium">
                      <GitCompare className="size-4" /> Comparer deux révisions
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Gauche">
                        <select
                          className={selectClass}
                          value={compareLeft ?? ""}
                          onChange={(event) => setCompareLeft(Number(event.target.value))}
                        >
                          {control.revisions.map((revision) => (
                            <option key={revision.strategy_revision} value={revision.strategy_revision}>
                              r{revision.strategy_revision}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Droite">
                        <select
                          className={selectClass}
                          value={compareRight ?? ""}
                          onChange={(event) => setCompareRight(Number(event.target.value))}
                        >
                          {control.revisions.map((revision) => (
                            <option key={revision.strategy_revision} value={revision.strategy_revision}>
                              r{revision.strategy_revision}
                            </option>
                          ))}
                        </select>
                      </Field>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => void requestComparison()}
                      disabled={control.busyAction !== null || !control.revisions.length}
                    >
                      <GitCompare className="size-4" /> Comparer via API
                    </Button>
                    {comparison ? (
                      <div className="space-y-2 rounded-md bg-muted/30 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <Badge tone={comparison.identical ? "success" : "warning"}>
                            {comparison.identical ? "identiques" : "différentes"}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            r{comparison.left_revision} → r{comparison.right_revision}
                          </span>
                        </div>
                        <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border bg-background p-3 text-[11px] leading-relaxed">
                          {comparison.unified_diff || "Aucune différence textuelle."}
                        </pre>
                      </div>
                    ) : null}
                  </div>

                  <div className="space-y-3 rounded-lg border p-4">
                    <div className="flex items-center gap-2 font-medium">
                      <Eye className="size-4" /> Prompt preview canonique
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Phase">
                        <select
                          className={selectClass}
                          value={previewPhase}
                          onChange={(event) => setPreviewPhase(event.target.value as PromptPreviewPhase)}
                        >
                          <option value="MARKET_SELECTION">MARKET_SELECTION</option>
                          <option value="FINAL_DECISION">FINAL_DECISION</option>
                        </select>
                      </Field>
                      <Field label="Agressivité">
                        <input
                          className={inputClass}
                          type="number"
                          min="1"
                          max="10"
                          step="1"
                          value={previewAggressiveness}
                          onChange={(event) => setPreviewAggressiveness(event.target.value)}
                          required
                        />
                      </Field>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => void requestPreview()}
                      disabled={control.busyAction !== null || selectedRevisionNumber === null}
                    >
                      <Eye className="size-4" /> Prévisualiser via API
                    </Button>
                    {preview && previewParts ? (
                      <div className="space-y-3">
                        <div className="rounded-md border p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <Badge tone="danger">Contrat Agent protégé</Badge>
                            <span className="text-xs">{preview.base_agent_contract_version}</span>
                          </div>
                          <pre className="max-h-52 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed">
                            {previewParts.protectedContract}
                          </pre>
                        </div>
                        <div className="rounded-md border p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <Badge tone="info">Stratégie opérateur</Badge>
                            <Digest value={preview.strategy_prompt_digest} />
                          </div>
                          <pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed">
                            {previewParts.operatorStrategy}
                          </pre>
                        </div>
                        <div className="rounded-md border p-3">
                          <Badge tone="warning">Contexte agressivité</Badge>
                          <pre className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed">
                            {previewParts.aggressiveness}
                          </pre>
                        </div>
                        <div className="rounded-md border border-dashed p-3 text-xs">
                          <div className="mb-1 flex items-center gap-2">
                            <Badge>Input dynamique futur</Badge>
                            <span className="font-mono">{preview.dynamic_input_model}</span>
                          </div>
                          <p className="text-muted-foreground">
                            dynamic_input = null. {preview.note}
                          </p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <CardTitle>Builder Campaign PAPER</CardTitle>
              <CardDescription>
                Une modification structurelle crée toujours une nouvelle Campaign. Le backend reste
                seul juge de la validité de CampaignConfiguration. Les valeurs préremplies sont un
                profil de saisie opérateur, pas des valeurs par défaut serveur.
              </CardDescription>
            </div>
            <Badge>{CONTROL_CONFIGURATION_VERSION}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {!control.selectedStrategy || selectedRevisionNumber === null ? (
            <p className="text-sm text-muted-foreground">
              Sélectionne une StrategyRevision avant de créer une Campaign.
            </p>
          ) : (
            <form className="space-y-6" onSubmit={submitCampaign}>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <Field label="Strategy">
                  <input
                    className={inputClass}
                    value={`${control.selectedStrategy.strategy_name} · r${selectedRevisionNumber}`}
                    readOnly
                  />
                </Field>
                <Field label="Modèle LLM">
                  <select
                    className={selectClass}
                    value={campaignDraft.llmModel}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({
                        ...current,
                        llmModel: event.target.value as LlmModel,
                      }))
                    }
                  >
                    <option value="gpt-5.6-luna">GPT-5.6 Luna</option>
                    <option value="gpt-5.6-sol">GPT-5.6 Sol</option>
                  </select>
                </Field>
                <Field label="Agressivité" hint="1 à 10 ; contexte stratégique, jamais un bypass Risk.">
                  <input
                    className={inputClass}
                    type="number"
                    min="1"
                    max="10"
                    step="1"
                    value={campaignDraft.aggressiveness}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, aggressiveness: event.target.value }))
                    }
                    required
                  />
                </Field>
                <Field label="Cadence (s)">
                  <input
                    className={inputClass}
                    type="number"
                    min="0.001"
                    step="any"
                    value={campaignDraft.cadenceSeconds}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, cadenceSeconds: event.target.value }))
                    }
                    required
                  />
                </Field>
                <Field label="Capital PAPER initial">
                  <input
                    className={inputClass}
                    inputMode="decimal"
                    value={campaignDraft.initialCapital}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, initialCapital: event.target.value }))
                    }
                    required
                  />
                </Field>
                <Field label="Actif de règlement">
                  <input
                    className={inputClass}
                    value={campaignDraft.settlementAsset}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, settlementAsset: event.target.value }))
                    }
                    maxLength={16}
                    required
                  />
                </Field>
                <Field label="Fee rate" hint="Fraction, ex. 0.001 = 0,1 %. ">
                  <input
                    className={inputClass}
                    inputMode="decimal"
                    value={campaignDraft.feeRate}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, feeRate: event.target.value }))
                    }
                    required
                  />
                </Field>
                <Field label="Spread (bps)">
                  <input
                    className={inputClass}
                    inputMode="decimal"
                    value={campaignDraft.spreadBps}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, spreadBps: event.target.value }))
                    }
                    required
                  />
                </Field>
                <Field label="Slippage (bps)">
                  <input
                    className={inputClass}
                    inputMode="decimal"
                    value={campaignDraft.slippageBps}
                    onChange={(event) =>
                      setCampaignDraft((current) => ({ ...current, slippageBps: event.target.value }))
                    }
                    required
                  />
                </Field>
              </div>

              <div className="rounded-lg border p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">Univers exécutable PAPER</p>
                    <p className="text-xs text-muted-foreground">
                      Chaque ligne est un ExecutableMarket canonique. FUTURE daté n’est jamais proposé.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setCampaignDraft((current) => ({
                        ...current,
                        markets: [...current.markets, { symbol: "", market_type: "SPOT" }],
                      }))
                    }
                  >
                    <Plus className="size-3.5" /> Ajouter un marché
                  </Button>
                </div>
                <div className="space-y-2">
                  {campaignDraft.markets.map((market, index) => (
                    <div key={index} className="grid gap-2 sm:grid-cols-[1fr_180px_auto]">
                      <input
                        className={inputClass}
                        value={market.symbol}
                        onChange={(event) => updateMarket(index, { symbol: event.target.value })}
                        placeholder="BTC/USD"
                        required
                      />
                      <select
                        className={selectClass}
                        value={market.market_type}
                        onChange={(event) =>
                          updateMarket(index, {
                            market_type: event.target.value as ExecutableMarketResponse["market_type"],
                          })
                        }
                      >
                        <option value="SPOT">SPOT</option>
                        <option value="PERPETUAL">PERPETUAL</option>
                      </select>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => removeMarket(index)}
                        disabled={campaignDraft.markets.length === 1}
                        aria-label="Retirer ce marché"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <div className="space-y-4 rounded-lg border p-4">
                  <div className="flex items-center gap-2 font-medium">
                    <ShieldCheck className="size-4" /> Risk Engine — paramètres exposés
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Ces champs configurent le Risk backend ; aucun calcul Risk n’est reproduit ici.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Max order notional">
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.riskMaxOrderNotional}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            riskMaxOrderNotional: event.target.value,
                          }))
                        }
                        required
                      />
                    </Field>
                    <Field label="Réduction de quantité autorisée">
                      <select
                        className={selectClass}
                        value={campaignDraft.riskAllowQuantityReduction ? "yes" : "no"}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            riskAllowQuantityReduction: event.target.value === "yes",
                          }))
                        }
                      >
                        <option value="yes">Oui</option>
                        <option value="no">Non</option>
                      </select>
                    </Field>
                  </div>
                  <Field
                    label="Paires Risk autorisées"
                    hint="Une paire par ligne ou séparée par virgule. Le backend exige que chaque marché exécutable soit couvert."
                  >
                    <textarea
                      className={`${textareaClass} min-h-24 font-mono text-xs`}
                      value={campaignDraft.riskAllowedPairs}
                      onChange={(event) =>
                        setCampaignDraft((current) => ({
                          ...current,
                          riskAllowedPairs: event.target.value,
                        }))
                      }
                      required
                    />
                  </Field>
                </div>

                <div className="space-y-4 rounded-lg border p-4">
                  <div className="flex items-center gap-2 font-medium">
                    <Database className="size-4" /> PERPETUAL déterministe
                    {hasPerpetual ? <Badge tone="warning">utilisé</Badge> : <Badge>inactif</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Marge ISOLATED imposée par le backend. Le levier est une configuration
                    déterministe, jamais une sortie LLM.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Marge">
                      <input className={inputClass} value="ISOLATED" readOnly />
                    </Field>
                    <Field label="Levier PAPER">
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.derivativeLeverage}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            derivativeLeverage: event.target.value,
                          }))
                        }
                        required
                      />
                    </Field>
                    <Field label="Levier Risk max">
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.riskMaxDerivativeLeverage}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            riskMaxDerivativeLeverage: event.target.value,
                          }))
                        }
                        required
                      />
                    </Field>
                    <Field
                      label="Position notional max"
                      hint={hasPerpetual ? "Requis par le backend pour PERPETUAL." : "Peut rester vide sans PERPETUAL."}
                    >
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.riskMaxDerivativePositionNotional}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            riskMaxDerivativePositionNotional: event.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field
                      label="Exposition dérivée totale max"
                      hint={hasPerpetual ? "Requis par le backend pour PERPETUAL." : "Peut rester vide sans PERPETUAL."}
                    >
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.riskMaxTotalDerivativeExposure}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            riskMaxTotalDerivativeExposure: event.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label="Liquidation buffer ratio">
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={campaignDraft.liquidationBufferRatio}
                        onChange={(event) =>
                          setCampaignDraft((current) => ({
                            ...current,
                            liquidationBufferRatio: event.target.value,
                          }))
                        }
                        required
                      />
                    </Field>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border p-4">
                <div className="mb-4 flex items-center gap-2 font-medium">
                  <Bot className="size-4" /> Deadlines de cycle
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Field label="Market timeout (s)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0.001"
                      step="any"
                      value={campaignDraft.marketTimeoutSeconds}
                      onChange={(event) =>
                        setCampaignDraft((current) => ({
                          ...current,
                          marketTimeoutSeconds: event.target.value,
                        }))
                      }
                      required
                    />
                  </Field>
                  <Field label="Agent timeout (s)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0.001"
                      step="any"
                      value={campaignDraft.agentTimeoutSeconds}
                      onChange={(event) =>
                        setCampaignDraft((current) => ({
                          ...current,
                          agentTimeoutSeconds: event.target.value,
                        }))
                      }
                      required
                    />
                  </Field>
                  <Field label="Broker timeout (s)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0.001"
                      step="any"
                      value={campaignDraft.brokerTimeoutSeconds}
                      onChange={(event) =>
                        setCampaignDraft((current) => ({
                          ...current,
                          brokerTimeoutSeconds: event.target.value,
                        }))
                      }
                      required
                    />
                  </Field>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/20 p-4">
                <div>
                  <p className="font-medium">Créer une nouvelle Campaign immuable</p>
                  <p className="text-xs text-muted-foreground">
                    Une Campaign existante n’est jamais éditée. Changer ces paramètres puis soumettre
                    produit un nouvel identifiant et de nouveaux digests backend.
                  </p>
                </div>
                <Button type="submit" disabled={control.busyAction !== null}>
                  <Plus className="size-4" /> Créer Campaign
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Campaigns persistées</CardTitle>
          <CardDescription>
            Activation fraîche et reprise sont deux commandes distinctes. Le backend refuse les
            incompatibilités et l’activation d’une Campaign déjà exécutée sans resume explicite.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {control.campaigns.length ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {control.campaigns.map((campaign) => {
                const strategy = control.strategies.find(
                  (item) => item.strategy_id === campaign.strategy_id,
                );
                const knownRuns = control.paperRuns.items.filter(
                  (run) => run.campaign_id === campaign.campaign_id,
                );
                const isActive = activeCampaign?.campaign_id === campaign.campaign_id;
                return (
                  <div key={campaign.campaign_id} className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-semibold">
                            {strategy?.strategy_name ?? shortUuid(campaign.strategy_id)} · r
                            {campaign.strategy_revision}
                          </p>
                          {isActive ? <Badge tone="success">active</Badge> : null}
                        </div>
                        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                          campaign {campaign.campaign_id}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          créée {formatTimestamp(campaign.created_at)}
                        </p>
                      </div>
                      <Badge tone="info">{campaign.configuration.llm_model}</Badge>
                    </div>

                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      <div className="rounded-md bg-muted/30 p-3 text-xs">
                        <span className="text-muted-foreground">Agressivité</span>
                        <p className="mt-1 font-semibold">{campaign.configuration.aggressiveness}/10</p>
                      </div>
                      <div className="rounded-md bg-muted/30 p-3 text-xs">
                        <span className="text-muted-foreground">Cadence</span>
                        <p className="mt-1 font-semibold">
                          {campaign.configuration.trading_cadence_seconds}s
                        </p>
                      </div>
                      <div className="rounded-md bg-muted/30 p-3 text-xs">
                        <span className="text-muted-foreground">Runs connus</span>
                        <p className="mt-1 font-semibold">{knownRuns.length}</p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {campaign.configuration.paper_executable_markets.map((market) => (
                        <Badge
                          key={`${market.market_type}:${market.symbol}`}
                          tone={market.market_type === "PERPETUAL" ? "warning" : "neutral"}
                        >
                          {market.market_type}:{market.symbol}
                        </Badge>
                      ))}
                    </div>

                    <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
                      <div>
                        <dt className="text-muted-foreground">strategy_prompt_digest</dt>
                        <dd><Digest value={campaign.strategy_prompt_digest} /></dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">configuration_digest</dt>
                        <dd><Digest value={campaign.configuration_digest} /></dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">experiment</dt>
                        <dd>{campaign.experiment_protocol_version}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">experiment_digest</dt>
                        <dd><Digest value={campaign.experiment_digest} /></dd>
                      </div>
                    </dl>

                    {knownRuns.length ? (
                      <div className="mt-4 space-y-2 rounded-md border bg-muted/20 p-3 text-xs">
                        {knownRuns.slice(0, 3).map((run) => (
                          <div key={run.paper_run_id} className="flex flex-wrap justify-between gap-2">
                            <span className="font-mono">{shortUuid(run.paper_run_id)}</span>
                            <span>from {shortUuid(run.resumed_from_paper_run_id)}</span>
                            <span>{run.recovery_version ?? "fresh"}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2 border-t pt-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void control.activateCampaign(campaign.campaign_id)}
                        disabled={control.busyAction !== null || engine?.status === "RUNNING"}
                      >
                        <Play className="size-3.5" /> Activation fraîche
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void control.resumeCampaign(campaign.campaign_id)}
                        disabled={control.busyAction !== null || engine?.status === "RUNNING"}
                      >
                        <RotateCcw className="size-3.5" /> Reprise explicite
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              Aucune Campaign persistée.
            </p>
          )}
          {control.paperRuns.total > control.paperRuns.items.length ? (
            <p className="mt-3 text-xs text-muted-foreground">
              La vue charge les 100 PAPER runs les plus récents ; le backend reste autorité pour tout
              conflit d’activation/reprise au-delà de cette fenêtre d’affichage.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
