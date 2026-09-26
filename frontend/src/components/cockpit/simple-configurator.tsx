"use client";

import {
  Bot,
  Check,
  CircleDollarSign,
  Play,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ControlPlaneController } from "@/hooks/use-control-plane";
import type { ExecutableMarketType, LlmModel, SessionResponse, TradingStyle } from "@/lib/api/types";
import {
  DEFAULT_MARKET_DISCOVERY_POLICY,
  TRADING_STYLE_MAPPING_VERSION,
  TRADING_STYLE_UI_METADATA,
  buildSessionCampaignConfiguration,
  initialSessionStyleValues,
  tradingStyleRecommendations,
  type SessionMarketSelectionMode,
  type SessionRiskProfile,
} from "@/lib/session-config";
import { cn } from "@/lib/utils";

const inputClass =
  "h-11 w-full rounded-lg border bg-background px-3 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";
const textareaClass =
  "min-h-32 w-full rounded-lg border bg-background px-3 py-3 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";

const PROFILE_COPY: Record<Exclude<SessionRiskProfile, "custom">, { label: string; detail: string }> = {
  prudent: {
    label: "Prudent",
    detail: "Ordre max 5 % du capital, levier PERPETUAL 1× et exposition dérivée très limitée.",
  },
  balanced: {
    label: "Équilibré",
    detail: "Ordre max 10 % du capital, levier PERPETUAL 2× et limites intermédiaires.",
  },
  aggressive: {
    label: "Agressif",
    detail: "Ordre max 20 % du capital, levier PERPETUAL 3× et enveloppe d’exposition plus large.",
  },
};

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint ? <span className="text-xs leading-relaxed text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

function ChoiceCard({
  active,
  title,
  detail,
  onClick,
}: {
  active: boolean;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border p-4 text-left transition",
        active ? "border-primary bg-primary/10 shadow-sm" : "bg-background hover:bg-muted/40",
      )}
    >
      <span className="flex items-center justify-between gap-3">
        <span className="font-semibold">{title}</span>
        {active ? <Check className="size-4 text-primary" /> : null}
      </span>
      <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{detail}</span>
    </button>
  );
}

function numberString(value: number): string {
  return Number.isFinite(value) ? String(value) : "";
}

export function SimpleConfigurator({
  control,
  session = null,
  onSaved,
  onCancel,
}: {
  control: ControlPlaneController;
  session?: SessionResponse | null;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const config = session?.configuration ?? null;
  const discovery = config?.market_discovery;
  const editing = session !== null;
  const initialStyle = initialSessionStyleValues(config, editing);

  const [name, setName] = useState(
    session?.name ?? `Session PAPER ${new Date().toISOString().slice(0, 16).replace("T", " ")}`,
  );
  const [marketType, setMarketType] = useState<ExecutableMarketType>(
    config?.paper_executable_markets[0]?.market_type ?? "SPOT",
  );
  const [marketSelectionMode, setMarketSelectionMode] = useState<SessionMarketSelectionMode>(
    session?.market_mode ?? "AUTOMATIC_AI",
  );
  const [pairs, setPairs] = useState(
    config?.paper_executable_markets.map((market) => market.symbol).join("\n") ?? "BTC/USD",
  );
  const [capital, setCapital] = useState(config?.paper_initial_capital ?? "1000");
  const [model, setModel] = useState<LlmModel>(config?.llm_model ?? "gpt-5.6-luna");
  const [aggressiveness, setAggressiveness] = useState(config?.aggressiveness ?? 5);
  const [tradingStyle, setTradingStyle] = useState<TradingStyle | null>(initialStyle.tradingStyle);
  const [prompt, setPrompt] = useState(
    session?.instructions ??
      "Cherche des opportunités cohérentes avec le contexte de marché. Privilégie la qualité du signal à la fréquence des trades et utilise HOLD quand l'opportunité n'est pas assez claire.",
  );
  const [riskProfile, setRiskProfile] = useState<SessionRiskProfile>(editing ? "custom" : "balanced");
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [cadence, setCadence] = useState(numberString(initialStyle.tradingCadenceSeconds));
  const [feeRate, setFeeRate] = useState(config?.paper_fee_rate ?? "0.001");
  const [spreadBps, setSpreadBps] = useState(config?.paper_spread_bps ?? "2");
  const [slippageBps, setSlippageBps] = useState(config?.paper_slippage_bps ?? "2");
  const [customMaxOrder, setCustomMaxOrder] = useState(config?.risk_max_order_notional ?? "100");
  const [customLeverage, setCustomLeverage] = useState(config?.paper_derivative_leverage ?? "1");
  const [customMaxLeverage, setCustomMaxLeverage] = useState(config?.risk_max_derivative_leverage ?? "1");
  const [customPositionNotional, setCustomPositionNotional] = useState(
    config?.risk_max_derivative_position_notional ?? "250",
  );
  const [customTotalExposure, setCustomTotalExposure] = useState(
    config?.risk_max_total_derivative_exposure ?? "500",
  );
  const [customLiquidationBuffer, setCustomLiquidationBuffer] = useState(
    config?.risk_derivative_liquidation_buffer_ratio ?? "1.10",
  );
  const [customAllowedPairs, setCustomAllowedPairs] = useState(
    config?.risk_allowed_pairs?.join("\n") ?? "",
  );
  const [marketTimeout, setMarketTimeout] = useState(numberString(config?.cycle_market_timeout_seconds ?? 20));
  const [agentTimeout, setAgentTimeout] = useState(numberString(config?.cycle_agent_timeout_seconds ?? 35));
  const [brokerTimeout, setBrokerTimeout] = useState(numberString(config?.cycle_broker_timeout_seconds ?? 5));

  const [catalogRefresh, setCatalogRefresh] = useState(
    numberString(discovery?.catalog_refresh_seconds ?? DEFAULT_MARKET_DISCOVERY_POLICY.catalog_refresh_seconds),
  );
  const [watchlistRefresh, setWatchlistRefresh] = useState(
    numberString(initialStyle.watchlistRefreshSeconds),
  );
  const [refreshTimeout, setRefreshTimeout] = useState(
    numberString(discovery?.refresh_timeout_seconds ?? DEFAULT_MARKET_DISCOVERY_POLICY.refresh_timeout_seconds),
  );
  const [candidateProbeLimit, setCandidateProbeLimit] = useState(
    numberString(discovery?.candidate_probe_limit ?? DEFAULT_MARKET_DISCOVERY_POLICY.candidate_probe_limit),
  );
  const [candidateLimit, setCandidateLimit] = useState(
    numberString(discovery?.candidate_limit ?? DEFAULT_MARKET_DISCOVERY_POLICY.candidate_limit),
  );
  const [watchlistLimit, setWatchlistLimit] = useState(
    numberString(discovery?.watchlist_limit ?? DEFAULT_MARKET_DISCOVERY_POLICY.watchlist_limit),
  );
  const [maxSnapshotAge, setMaxSnapshotAge] = useState(
    numberString(discovery?.max_snapshot_age_seconds ?? DEFAULT_MARKET_DISCOVERY_POLICY.max_snapshot_age_seconds),
  );
  const [minWindowObservations, setMinWindowObservations] = useState(
    numberString(discovery?.min_window_observations ?? DEFAULT_MARKET_DISCOVERY_POLICY.min_window_observations),
  );
  const [requireCompleteWindow, setRequireCompleteWindow] = useState(
    discovery?.require_complete_window ?? DEFAULT_MARKET_DISCOVERY_POLICY.require_complete_window,
  );
  const [validationError, setValidationError] = useState<string | null>(null);

  const styleMetadata = tradingStyle ? TRADING_STYLE_UI_METADATA[tradingStyle] : null;
  const styleMappingVersion = tradingStyle
    ? config?.trading_style_mapping_version ?? TRADING_STYLE_MAPPING_VERSION
    : null;

  const configurationResult = useMemo(() => {
    try {
      if (!name.trim()) throw new Error("Donne un nom à la Session.");
      if (!prompt.trim()) throw new Error("Ajoute des instructions pour l’IA.");
      if (aggressiveness < 1 || aggressiveness > 10) {
        throw new Error("L’agressivité doit être comprise entre 1 et 10.");
      }
      const configuration = buildSessionCampaignConfiguration({
        marketType,
        marketSelectionMode,
        pairs,
        capital,
        model,
        aggressiveness,
        tradingStyle,
        riskProfile,
        cadence,
        feeRate,
        spreadBps,
        slippageBps,
        customMaxOrder,
        customLeverage,
        customMaxLeverage,
        customPositionNotional,
        customTotalExposure,
        customLiquidationBuffer,
        customAllowedPairs,
        marketTimeout,
        agentTimeout,
        brokerTimeout,
        discovery: {
          catalog_refresh_seconds: Number(catalogRefresh),
          watchlist_refresh_seconds: Number(watchlistRefresh),
          refresh_timeout_seconds: Number(refreshTimeout),
          candidate_probe_limit: Number(candidateProbeLimit),
          candidate_limit: Number(candidateLimit),
          watchlist_limit: Number(watchlistLimit),
          max_snapshot_age_seconds: Number(maxSnapshotAge),
          min_window_observations: Number(minWindowObservations),
          require_complete_window: requireCompleteWindow,
        },
      });
      return { configuration, error: null };
    } catch (error) {
      return {
        configuration: null,
        error: error instanceof Error ? error.message : "Configuration invalide.",
      };
    }
  }, [
    agentTimeout,
    aggressiveness,
    brokerTimeout,
    cadence,
    candidateLimit,
    candidateProbeLimit,
    capital,
    catalogRefresh,
    customAllowedPairs,
    customLeverage,
    customLiquidationBuffer,
    customMaxLeverage,
    customMaxOrder,
    customPositionNotional,
    customTotalExposure,
    feeRate,
    marketSelectionMode,
    marketTimeout,
    marketType,
    maxSnapshotAge,
    minWindowObservations,
    model,
    name,
    pairs,
    prompt,
    refreshTimeout,
    requireCompleteWindow,
    riskProfile,
    slippageBps,
    spreadBps,
    tradingStyle,
    watchlistLimit,
    watchlistRefresh,
  ]);

  const busy = control.busyAction !== null;
  const runningEdit = session?.status === "RUNNING";
  const operationError = control.feedback?.tone === "error" ? control.feedback.message : null;

  function applyRecommendedStyleValues() {
    if (!tradingStyle) return;
    const recommendations = tradingStyleRecommendations(tradingStyle);
    setCadence(numberString(recommendations.tradingCadenceSeconds));
    setWatchlistRefresh(numberString(recommendations.watchlistRefreshSeconds));
  }

  async function submit(startNow: boolean) {
    setValidationError(null);
    if (!configurationResult.configuration) {
      setValidationError(configurationResult.error ?? "Configuration invalide.");
      return;
    }
    const result = editing
      ? await control.updateSession(session.session_id, {
          name: name.trim(),
          prompt: prompt.trim(),
          configuration: configurationResult.configuration,
        })
      : await control.createSession({
          name: name.trim(),
          prompt: prompt.trim(),
          configuration: configurationResult.configuration,
          startNow,
        });
    if (result) onSaved();
  }

  const marketModeHint = marketSelectionMode === "AUTOMATIC_AI"
    ? "La paire saisie sert de bootstrap/fallback. L’Agent peut découvrir d’autres marchés admissibles ; elle n’est pas une obligation de trader cet actif."
    : "L’Agent conserve BUY / SELL / HOLD mais ne travaille que dans la liste autorisée ci-dessous.";

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Sessions · PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">
            {editing ? "Modifier la Session" : "Nouvelle Session"}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Les choix essentiels sont visibles immédiatement. La configuration avancée expose les valeurs réellement envoyées au backend.
          </p>
        </div>
        {editing ? <Badge tone={runningEdit ? "warning" : "info"}>{runningEdit ? "En cours · arrêter avant modification" : "Édition versionnée"}</Badge> : null}
      </div>

      {runningEdit ? (
        <Card className="border-warning/35 bg-warning-subtle shadow-none">
          <CardContent className="py-4 text-sm text-warning-foreground">
            Cette Session est en cours. Le backend refuse toute mutation silencieuse : arrête-la depuis Sessions avant d’enregistrer une nouvelle version.
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Sparkles className="size-4" /> Configuration simple</CardTitle>
          <CardDescription>Nom, capital, marché, sélection, IA, style de trading, agressivité, Risk et instructions opérateur.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <Field label="Nom de la Session">
            <input className={inputClass} value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex. Test SPOT IA" />
          </Field>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Type de marché</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <ChoiceCard active={marketType === "SPOT"} title="SPOT" detail="Achat/vente au comptant, sans short ni levier." onClick={() => setMarketType("SPOT")} />
                <ChoiceCard active={marketType === "PERPETUAL"} title="PERPETUAL" detail="Contrats PAPER selon les capacités intégrées et caps Risk." onClick={() => setMarketType("PERPETUAL")} />
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Sélection des marchés</p>
              <div className="grid gap-2">
                <ChoiceCard active={marketSelectionMode === "AUTOMATIC_AI"} title="Automatique — laisser l’IA chercher les opportunités" detail="Discovery Kraken filtrée puis watchlist sélectionnée par le même Agent IA." onClick={() => setMarketSelectionMode("AUTOMATIC_AI")} />
                <ChoiceCard active={marketSelectionMode === "MANUAL"} title="Manuel — choisir les marchés" detail="Univers explicite fourni par l’opérateur ; aucune discovery dynamique." onClick={() => setMarketSelectionMode("MANUAL")} />
              </div>
            </div>
          </div>

          <Field label={marketSelectionMode === "AUTOMATIC_AI" ? "Paire bootstrap / fallback" : "Marchés autorisés"} hint={marketModeHint}>
            <textarea className={textareaClass} value={pairs} onChange={(event) => setPairs(event.target.value)} placeholder={marketSelectionMode === "MANUAL" ? "BTC/USD\nETH/USD\nSOL/USD" : "BTC/USD"} />
          </Field>

          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Capital PAPER">
              <div className="relative"><CircleDollarSign className="absolute left-3 top-3.5 size-4 text-muted-foreground" /><input className={`${inputClass} pl-9`} value={capital} onChange={(event) => setCapital(event.target.value)} inputMode="decimal" /></div>
            </Field>
            <Field label="Modèle IA">
              <select className={inputClass} value={model} onChange={(event) => setModel(event.target.value as LlmModel)}>
                <option value="gpt-5.6-luna">Luna</option>
                <option value="gpt-5.6-sol">Sol</option>
              </select>
            </Field>
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium">Style de trading</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Le style définit l’horizon stratégique. Il reste indépendant de l’agressivité, du mode de sélection des marchés et du profil Risk.
              </p>
            </div>
            {tradingStyle === null ? (
              <div className="rounded-lg border border-warning/35 bg-warning-subtle p-3 text-sm text-warning-foreground">
                Session historique : style hérité / non défini. Aucun style n’est inféré tant que tu ne choisis pas explicitement Scalping ou Swing.
              </div>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2">
              <ChoiceCard
                active={tradingStyle === "SCALP"}
                title={TRADING_STYLE_UI_METADATA.SCALP.label}
                detail={TRADING_STYLE_UI_METADATA.SCALP.detail}
                onClick={() => setTradingStyle("SCALP")}
              />
              <ChoiceCard
                active={tradingStyle === "SWING"}
                title={TRADING_STYLE_UI_METADATA.SWING.label}
                detail={TRADING_STYLE_UI_METADATA.SWING.detail}
                onClick={() => setTradingStyle("SWING")}
              />
            </div>
            {styleMetadata ? (
              <div className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-xs leading-relaxed text-muted-foreground">
                  <span className="font-medium text-foreground">Sélection actuelle : {styleMetadata.label}</span>
                  <span className="block">Timeframes stratégiques : {styleMetadata.timeframes.join(" · ")}</span>
                  <span className="block">
                    Valeurs conseillées à la création : cadence {styleMetadata.recommendedTradingCadenceSeconds} s · watchlist {styleMetadata.recommendedWatchlistRefreshSeconds} s.
                  </span>
                </div>
                <Button variant="outline" onClick={applyRecommendedStyleValues}>
                  Réappliquer les valeurs conseillées
                </Button>
              </div>
            ) : null}
          </div>

          <Field label={`Agressivité · ${aggressiveness}/10`} hint="Ce paramètre contextualise l’Agent ; le Risk Engine déterministe garde l’autorité finale.">
            <input type="range" min={1} max={10} value={aggressiveness} onChange={(event) => setAggressiveness(Number(event.target.value))} className="w-full" />
          </Field>

          <div className="space-y-2">
            <p className="text-sm font-medium">Profil Risk</p>
            <div className="grid gap-2 md:grid-cols-4">
              {(Object.keys(PROFILE_COPY) as Array<Exclude<SessionRiskProfile, "custom">>).map((profile) => (
                <ChoiceCard key={profile} active={riskProfile === profile} title={PROFILE_COPY[profile].label} detail={PROFILE_COPY[profile].detail} onClick={() => setRiskProfile(profile)} />
              ))}
              <ChoiceCard active={riskProfile === "custom"} title="Personnalisé" detail="Utilise exactement les caps saisis dans Configuration avancée." onClick={() => setRiskProfile("custom")} />
            </div>
          </div>

          <Field label="Instructions IA / opérateur" hint="Elles complètent le contrat Agent protégé. Toute modification crée une nouvelle version des instructions sans écraser l’historique.">
            <textarea className={textareaClass} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="cursor-pointer" onClick={() => setAdvancedOpen((value) => !value)}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2"><Settings2 className="size-4" /> Configuration avancée</CardTitle>
              <CardDescription className="mt-1">Style effectif, cadence, coûts PAPER, timeouts, caps Risk et paramètres Market Discovery.</CardDescription>
            </div>
            <Badge tone="neutral">{advancedOpen ? "Masquer" : "Afficher"}</Badge>
          </div>
        </CardHeader>
        {advancedOpen ? (
          <CardContent className="space-y-7 border-t pt-6">
            <section className="space-y-4">
              <div>
                <h3 className="font-semibold">Style stratégique effectif</h3>
                <p className="text-xs text-muted-foreground">Lecture seule du mapping stratégique ; les timeframes ne sont pas configurables indépendamment du style.</p>
              </div>
              {styleMetadata ? (
                <div className="grid gap-3 rounded-xl border bg-muted/20 p-4 md:grid-cols-3">
                  <div><p className="text-xs text-muted-foreground">Style</p><p className="mt-1 font-medium">{styleMetadata.label}</p></div>
                  <div><p className="text-xs text-muted-foreground">Mapping</p><p className="mt-1 font-medium">{styleMappingVersion}</p></div>
                  <div><p className="text-xs text-muted-foreground">Timeframes stratégiques</p><p className="mt-1 font-medium">{styleMetadata.timeframes.join(" · ")}</p></div>
                </div>
              ) : (
                <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">
                  Style : Hérité / non défini · mapping et timeframes non inférés.
                </div>
              )}
            </section>

            <section className="space-y-4 border-t pt-6">
              <div><h3 className="font-semibold">Runtime & coûts PAPER</h3><p className="text-xs text-muted-foreground">Valeurs effectivement persistées dans la prochaine version de configuration.</p></div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <Field label="Cadence stratégique (s)"><input className={inputClass} value={cadence} onChange={(e) => setCadence(e.target.value)} /></Field>
                <Field label="Frais PAPER"><input className={inputClass} value={feeRate} onChange={(e) => setFeeRate(e.target.value)} /></Field>
                <Field label="Spread (bps)"><input className={inputClass} value={spreadBps} onChange={(e) => setSpreadBps(e.target.value)} /></Field>
                <Field label="Slippage (bps)"><input className={inputClass} value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)} /></Field>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Timeout marché (s)"><input className={inputClass} value={marketTimeout} onChange={(e) => setMarketTimeout(e.target.value)} /></Field>
                <Field label="Timeout Agent (s)"><input className={inputClass} value={agentTimeout} onChange={(e) => setAgentTimeout(e.target.value)} /></Field>
                <Field label="Timeout Broker (s)"><input className={inputClass} value={brokerTimeout} onChange={(e) => setBrokerTimeout(e.target.value)} /></Field>
              </div>
            </section>

            <section className="space-y-4 border-t pt-6">
              <div><h3 className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" /> Risk personnalisé</h3><p className="text-xs text-muted-foreground">Ces champs sont appliqués directement lorsque le profil « Personnalisé » est sélectionné.</p></div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <Field label="Max notional / ordre"><input className={inputClass} value={customMaxOrder} onChange={(e) => setCustomMaxOrder(e.target.value)} /></Field>
                <Field label="Levier PAPER"><input className={inputClass} value={customLeverage} onChange={(e) => setCustomLeverage(e.target.value)} disabled={marketType !== "PERPETUAL"} /></Field>
                <Field label="Levier Risk max"><input className={inputClass} value={customMaxLeverage} onChange={(e) => setCustomMaxLeverage(e.target.value)} disabled={marketType !== "PERPETUAL"} /></Field>
                <Field label="Notional position dérivée max"><input className={inputClass} value={customPositionNotional} onChange={(e) => setCustomPositionNotional(e.target.value)} disabled={marketType !== "PERPETUAL"} /></Field>
                <Field label="Exposition dérivée totale max"><input className={inputClass} value={customTotalExposure} onChange={(e) => setCustomTotalExposure(e.target.value)} disabled={marketType !== "PERPETUAL"} /></Field>
                <Field label="Buffer liquidation"><input className={inputClass} value={customLiquidationBuffer} onChange={(e) => setCustomLiquidationBuffer(e.target.value)} /></Field>
              </div>
              {marketSelectionMode === "AUTOMATIC_AI" ? (
                <Field label="Whitelist Risk optionnelle" hint="Vide = la discovery dynamique n’est pas réduite à une whitelist statique. Si renseignée, les paires bootstrap doivent y appartenir.">
                  <textarea className={textareaClass} value={customAllowedPairs} onChange={(e) => setCustomAllowedPairs(e.target.value)} placeholder="BTC/USD\nETH/USD" />
                </Field>
              ) : (
                <p className="rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">En mode Manuel, la whitelist Risk est automatiquement alignée sur la liste des marchés autorisés.</p>
              )}
            </section>

            {marketSelectionMode === "AUTOMATIC_AI" ? (
              <section className="space-y-4 border-t pt-6">
                <div><h3 className="flex items-center gap-2 font-semibold"><Waves className="size-4" /> Market Discovery</h3><p className="text-xs text-muted-foreground">Valeurs effectives persistées ; le style ne les modifie que via l’action explicite « Réappliquer les valeurs conseillées ».</p></div>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <Field label="Catalog refresh (s)"><input className={inputClass} value={catalogRefresh} onChange={(e) => setCatalogRefresh(e.target.value)} /></Field>
                  <Field label="Watchlist refresh (s)"><input className={inputClass} value={watchlistRefresh} onChange={(e) => setWatchlistRefresh(e.target.value)} /></Field>
                  <Field label="Refresh timeout (s)"><input className={inputClass} value={refreshTimeout} onChange={(e) => setRefreshTimeout(e.target.value)} /></Field>
                  <Field label="Candidate probe limit"><input className={inputClass} value={candidateProbeLimit} onChange={(e) => setCandidateProbeLimit(e.target.value)} /></Field>
                  <Field label="Candidate limit"><input className={inputClass} value={candidateLimit} onChange={(e) => setCandidateLimit(e.target.value)} /></Field>
                  <Field label="Watchlist limit"><input className={inputClass} value={watchlistLimit} onChange={(e) => setWatchlistLimit(e.target.value)} /></Field>
                  <Field label="Max snapshot age (s)"><input className={inputClass} value={maxSnapshotAge} onChange={(e) => setMaxSnapshotAge(e.target.value)} /></Field>
                  <Field label="Min window observations"><input className={inputClass} value={minWindowObservations} onChange={(e) => setMinWindowObservations(e.target.value)} /></Field>
                  <label className="flex items-center gap-3 rounded-lg border bg-muted/20 px-3 py-3 text-sm"><input type="checkbox" checked={requireCompleteWindow} onChange={(e) => setRequireCompleteWindow(e.target.checked)} /><span><strong>Require complete window</strong><span className="block text-xs text-muted-foreground">Refuse les candidats dont la fenêtre d’observations est incomplète.</span></span></label>
                </div>
              </section>
            ) : null}
          </CardContent>
        ) : null}
      </Card>

      {(validationError || configurationResult.error || operationError) ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive-subtle-foreground">
          {validationError ?? configurationResult.error ?? operationError}
        </div>
      ) : null}

      <Card className="border-primary/25 bg-primary/5">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="flex items-center gap-2 font-semibold"><Bot className="size-4" /> {editing ? "Enregistrer une nouvelle version" : "Créer la Session"}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {editing
                ? "Le nom peut être modifié directement ; prompt et configuration créent de nouveaux faits immuables uniquement lorsqu’ils changent."
                : "La création backend est atomique : aucune configuration partielle n’est conservée en cas d’échec de persistance."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {onCancel ? <Button variant="outline" onClick={onCancel} disabled={busy}>Annuler</Button> : null}
            <Button variant="outline" onClick={() => void submit(false)} disabled={busy || runningEdit || !configurationResult.configuration}>
              <Save className="size-4" /> {editing ? "Enregistrer" : "Créer"}
            </Button>
            {!editing ? (
              <Button onClick={() => void submit(true)} disabled={busy || !configurationResult.configuration}>
                <Play className="size-4" /> Créer et démarrer
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
