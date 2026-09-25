"use client";

import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
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
import type {
  CampaignConfiguration,
  ExecutableMarketResponse,
  LlmModel,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

type RiskProfile = "prudent" | "balanced" | "aggressive" | "custom";
type WizardStep = 1 | 2 | 3 | 4 | 5;
type DynamicCampaignConfiguration = Omit<CampaignConfiguration, "risk_allowed_pairs"> & {
  risk_allowed_pairs: string[] | null;
  market_discovery: {
    protocol_version: "market-discovery-v1";
    market_types: ExecutableMarketResponse["market_type"][];
    catalog_refresh_seconds: number;
    watchlist_refresh_seconds: number;
    refresh_timeout_seconds: number;
    candidate_probe_limit: number;
    candidate_limit: number;
    watchlist_limit: number;
    max_snapshot_age_seconds: number;
    min_window_observations: number;
    require_complete_window: boolean;
  };
};

const inputClass =
  "h-11 w-full rounded-lg border bg-background px-3 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";
const textareaClass =
  "min-h-36 w-full rounded-lg border bg-background px-3 py-3 text-sm shadow-sm outline-none transition focus:border-foreground/40 focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";

const PROFILE_COPY: Record<Exclude<RiskProfile, "custom">, { label: string; detail: string }> = {
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

const STEP_LABELS = ["Marché", "Capital", "IA", "Sécurité", "Résumé"];

function roundDecimal(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return String(Math.round(value * 100_000_000) / 100_000_000);
}

function parseMarkets(value: string, marketType: ExecutableMarketResponse["market_type"]) {
  const symbols = Array.from(
    new Set(
      value
        .split(/[\n,;]/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
  if (!symbols.length) throw new Error("Ajoute au moins une paire de départ, par exemple BTC/USD.");
  const quotes = new Set<string>();
  for (const symbol of symbols) {
    const parts = symbol.split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new Error(`Paire invalide : ${symbol}. Utilise le format BASE/QUOTE.`);
    }
    quotes.add(parts[1]);
  }
  if (quotes.size !== 1) {
    throw new Error("Toutes les paires de départ doivent utiliser le même actif de règlement.");
  }
  return {
    settlementAsset: Array.from(quotes)[0],
    markets: symbols.map((symbol) => ({ symbol, market_type: marketType })),
  };
}

function profileRisk(
  profile: Exclude<RiskProfile, "custom">,
  capital: number,
  marketType: ExecutableMarketResponse["market_type"],
) {
  const profileValues = {
    prudent: {
      orderFraction: 0.05,
      leverage: "1",
      positionFraction: 0.1,
      totalFraction: 0.2,
      buffer: "1.25",
    },
    balanced: {
      orderFraction: 0.1,
      leverage: "2",
      positionFraction: 0.2,
      totalFraction: 0.4,
      buffer: "1.15",
    },
    aggressive: {
      orderFraction: 0.2,
      leverage: "3",
      positionFraction: 0.35,
      totalFraction: 0.7,
      buffer: "1.10",
    },
  }[profile];

  return {
    maxOrderNotional: roundDecimal(capital * profileValues.orderFraction),
    derivativeLeverage: marketType === "PERPETUAL" ? profileValues.leverage : "1",
    maxDerivativeLeverage: marketType === "PERPETUAL" ? profileValues.leverage : "1",
    maxDerivativePositionNotional:
      marketType === "PERPETUAL" ? roundDecimal(capital * profileValues.positionFraction) : null,
    maxTotalDerivativeExposure:
      marketType === "PERPETUAL" ? roundDecimal(capital * profileValues.totalFraction) : null,
    liquidationBuffer: profileValues.buffer,
  };
}

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
        active ? "border-foreground bg-foreground text-background" : "bg-background hover:bg-muted/40",
      )}
    >
      <span className="flex items-center justify-between gap-3">
        <span className="font-semibold">{title}</span>
        {active ? <Check className="size-4" /> : null}
      </span>
      <span className={cn("mt-1 block text-xs leading-relaxed", active ? "text-background/70" : "text-muted-foreground")}>
        {detail}
      </span>
    </button>
  );
}

export function SimpleConfigurator({
  control,
  onCreated,
}: {
  control: ControlPlaneController;
  onCreated: () => void;
}) {
  const [step, setStep] = useState<WizardStep>(1);
  const [marketType, setMarketType] = useState<ExecutableMarketResponse["market_type"]>("SPOT");
  const [pairs, setPairs] = useState("BTC/USD");
  const [capital, setCapital] = useState("1000");
  const [model, setModel] = useState<LlmModel>("gpt-5.6-luna");
  const [aggressiveness, setAggressiveness] = useState(5);
  const [prompt, setPrompt] = useState(
    "Cherche des opportunités cohérentes avec le contexte de marché. Privilégie la qualité du signal à la fréquence des trades et utilise HOLD quand l'opportunité n'est pas assez claire.",
  );
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [testName, setTestName] = useState(() => `Test PAPER ${new Date().toISOString().slice(0, 19).replace("T", " ")}`);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [cadence, setCadence] = useState("30");
  const [feeRate, setFeeRate] = useState("0.001");
  const [spreadBps, setSpreadBps] = useState("2");
  const [slippageBps, setSlippageBps] = useState("2");
  const [customMaxOrder, setCustomMaxOrder] = useState("100");
  const [customLeverage, setCustomLeverage] = useState("1");
  const [customMaxLeverage, setCustomMaxLeverage] = useState("1");
  const [customPositionNotional, setCustomPositionNotional] = useState("250");
  const [customTotalExposure, setCustomTotalExposure] = useState("500");
  const [customLiquidationBuffer, setCustomLiquidationBuffer] = useState("1.10");
  const [customAllowedPairs, setCustomAllowedPairs] = useState("");
  const [marketTimeout, setMarketTimeout] = useState("20");
  const [agentTimeout, setAgentTimeout] = useState("35");
  const [brokerTimeout, setBrokerTimeout] = useState("5");
  const [validationError, setValidationError] = useState<string | null>(null);

  const plan = useMemo(() => {
    try {
      const numericCapital = Number(capital);
      if (!Number.isFinite(numericCapital) || numericCapital <= 0) {
        throw new Error("Le capital PAPER doit être un nombre strictement positif.");
      }
      if (!testName.trim()) throw new Error("Donne un nom à cette configuration de test.");
      if (!prompt.trim()) throw new Error("Ajoute des instructions pour l’IA.");
      const marketPlan = parseMarkets(pairs, marketType);
      const risk =
        riskProfile === "custom"
          ? {
              maxOrderNotional: customMaxOrder.trim(),
              derivativeLeverage: marketType === "PERPETUAL" ? customLeverage.trim() : "1",
              maxDerivativeLeverage: marketType === "PERPETUAL" ? customMaxLeverage.trim() : "1",
              maxDerivativePositionNotional:
                marketType === "PERPETUAL" ? customPositionNotional.trim() || null : null,
              maxTotalDerivativeExposure:
                marketType === "PERPETUAL" ? customTotalExposure.trim() || null : null,
              liquidationBuffer: customLiquidationBuffer.trim(),
            }
          : profileRisk(riskProfile, numericCapital, marketType);

      const allowedPairs =
        riskProfile === "custom" && customAllowedPairs.trim()
          ? Array.from(
              new Set(
                customAllowedPairs
                  .split(/[\n,;]/)
                  .map((item) => item.trim().toUpperCase())
                  .filter(Boolean),
              ),
            )
          : null;

      const configuration: DynamicCampaignConfiguration = {
        configuration_version: "paper-control-plane-config-v1",
        llm_model: model,
        aggressiveness,
        trading_cadence_seconds: Number(cadence),
        paper_initial_capital: capital.trim(),
        paper_settlement_asset: marketPlan.settlementAsset,
        paper_executable_markets: marketPlan.markets,
        market_discovery: {
          protocol_version: "market-discovery-v1",
          market_types: [marketType],
          catalog_refresh_seconds: 900,
          watchlist_refresh_seconds: 900,
          refresh_timeout_seconds: 45,
          candidate_probe_limit: 24,
          candidate_limit: 12,
          watchlist_limit: 6,
          max_snapshot_age_seconds: 120,
          min_window_observations: 2,
          require_complete_window: false,
        },
        paper_fee_rate: feeRate.trim(),
        paper_spread_bps: spreadBps.trim(),
        paper_slippage_bps: slippageBps.trim(),
        paper_derivative_leverage: risk.derivativeLeverage,
        paper_derivative_margin_mode: "ISOLATED",
        risk_max_order_notional: risk.maxOrderNotional,
        risk_allowed_pairs: allowedPairs,
        risk_allow_quantity_reduction: true,
        risk_max_derivative_leverage: risk.maxDerivativeLeverage,
        risk_max_derivative_position_notional: risk.maxDerivativePositionNotional,
        risk_max_total_derivative_exposure: risk.maxTotalDerivativeExposure,
        risk_derivative_liquidation_buffer_ratio: risk.liquidationBuffer,
        cycle_market_timeout_seconds: Number(marketTimeout),
        cycle_agent_timeout_seconds: Number(agentTimeout),
        cycle_broker_timeout_seconds: Number(brokerTimeout),
      };
      return { configuration: configuration as unknown as CampaignConfiguration, error: null };
    } catch (error) {
      return {
        configuration: null,
        error: error instanceof Error ? error.message : "Configuration invalide.",
      };
    }
  }, [
    aggressiveness,
    agentTimeout,
    brokerTimeout,
    cadence,
    capital,
    customAllowedPairs,
    customLeverage,
    customLiquidationBuffer,
    customMaxLeverage,
    customMaxOrder,
    customPositionNotional,
    customTotalExposure,
    feeRate,
    marketTimeout,
    marketType,
    model,
    pairs,
    prompt,
    riskProfile,
    slippageBps,
    spreadBps,
    testName,
  ]);

  const busy = control.busyAction === "create-paper-test";

  function nextStep() {
    setValidationError(null);
    if (step === 1) {
      try {
        parseMarkets(pairs, marketType);
      } catch (error) {
        setValidationError(error instanceof Error ? error.message : "Marché invalide.");
        return;
      }
    }
    if (step === 2 && (!Number.isFinite(Number(capital)) || Number(capital) <= 0)) {
      setValidationError("Le capital PAPER doit être un nombre strictement positif.");
      return;
    }
    if (step === 3 && !prompt.trim()) {
      setValidationError("Ajoute des instructions pour l’IA.");
      return;
    }
    setStep((current) => Math.min(5, current + 1) as WizardStep);
  }

  async function create(startNow: boolean) {
    if (!plan.configuration) {
      setValidationError(plan.error ?? "Configuration invalide.");
      return;
    }
    setValidationError(null);
    const result = await control.createPaperTest({
      name: testName.trim(),
      prompt: prompt.trim(),
      configuration: plan.configuration,
      startNow,
    });
    if (result) onCreated();
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Nouveau test PAPER</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">Configurer en quelques étapes</h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Le cockpit crée les objets techniques nécessaires en arrière-plan. Le Risk Engine backend reste l’autorité finale sur chaque ordre.
        </p>
      </div>

      <div className="grid grid-cols-5 gap-2" aria-label="Progression de la configuration">
        {STEP_LABELS.map((label, index) => {
          const number = index + 1;
          const active = number === step;
          const done = number < step;
          return (
            <button
              key={label}
              type="button"
              onClick={() => setStep(number as WizardStep)}
              className={cn(
                "rounded-lg border px-2 py-2 text-center text-[11px] transition sm:text-xs",
                active && "border-foreground bg-foreground text-background",
                done && !active && "bg-muted/60",
              )}
            >
              <span className="hidden sm:inline">{number} · </span>{label}
            </button>
          );
        })}
      </div>

      <Card className="shadow-none">
        {step === 1 ? (
          <>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Waves className="size-4" /> Quel marché tester ?</CardTitle>
              <CardDescription>Choisis le type de marché et une paire de départ/secours. Le backend découvrira ensuite périodiquement les marchés Kraken admissibles et le même Agent IA construira la watchlist.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <ChoiceCard active={marketType === "SPOT"} title="SPOT" detail="Achat et vente d’actifs détenus. Aucun short, aucun levier." onClick={() => setMarketType("SPOT")} />
                <ChoiceCard active={marketType === "PERPETUAL"} title="PERPETUAL" detail="Contrats linéaires PAPER, LONG/SHORT, marge isolée et limites de levier imposées par Risk." onClick={() => setMarketType("PERPETUAL")} />
              </div>
              <Field label="Paire de départ / secours" hint="Tu n’as plus besoin de renseigner toute la watchlist. Cette paire sert de bootstrap et de repli si Kraken ou l’IA de découverte est indisponible.">
                <input className={inputClass} value={pairs} onChange={(event) => setPairs(event.target.value)} placeholder="BTC/USD" />
              </Field>
            </CardContent>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><CircleDollarSign className="size-4" /> Quel capital PAPER ?</CardTitle>
              <CardDescription>Capital simulé uniquement. LIVE reste indisponible.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mx-auto max-w-lg">
                <Field label="Capital initial" hint="Le profil Risk simple convertira ensuite ce capital en limites explicites de notional et d’exposition.">
                  <input className={inputClass} inputMode="decimal" value={capital} onChange={(event) => setCapital(event.target.value)} placeholder="1000" />
                </Field>
              </div>
            </CardContent>
          </>
        ) : null}

        {step === 3 ? (
          <>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Bot className="size-4" /> Comment l’IA doit-elle travailler ?</CardTitle>
              <CardDescription>Le même Agent sélectionne périodiquement une watchlist, puis propose BUY, SELL ou HOLD dans les cycles. Risk reste l’autorité finale.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <ChoiceCard active={model === "gpt-5.6-luna"} title="GPT-5.6 Luna" detail="Modèle rapide pour les premiers tests et itérations." onClick={() => setModel("gpt-5.6-luna")} />
                <ChoiceCard active={model === "gpt-5.6-sol"} title="GPT-5.6 Sol" detail="Modèle plus capable, sélectionnable explicitement pour comparer les comportements." onClick={() => setModel("gpt-5.6-sol")} />
              </div>
              <Field label={`Agressivité : ${aggressiveness}/10`} hint="Ce contexte influence la stratégie de l’Agent. Il ne relève jamais les limites du Risk Engine.">
                <input type="range" min={1} max={10} step={1} value={aggressiveness} onChange={(event) => setAggressiveness(Number(event.target.value))} className="w-full accent-foreground" />
              </Field>
              <Field label="Instructions opérateur" hint="Décris ici le comportement stratégique souhaité. Aucun secret ou clé API ne doit être placé dans ce texte.">
                <textarea className={textareaClass} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              </Field>
            </CardContent>
          </>
        ) : null}

        {step === 4 ? (
          <>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4" /> Quel niveau de sécurité ?</CardTitle>
              <CardDescription>Ces profils sont uniquement des raccourcis UX vers les champs canoniques de CampaignConfiguration. Ils ne remplacent jamais Risk.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 lg:grid-cols-4">
                {(Object.keys(PROFILE_COPY) as Array<Exclude<RiskProfile, "custom">>).map((profile) => (
                  <ChoiceCard key={profile} active={riskProfile === profile} title={PROFILE_COPY[profile].label} detail={PROFILE_COPY[profile].detail} onClick={() => setRiskProfile(profile)} />
                ))}
                <ChoiceCard active={riskProfile === "custom"} title="Personnalisé" detail="Expose les limites Risk et paramètres PAPER avancés sans les déplacer dans le frontend." onClick={() => { setRiskProfile("custom"); setAdvancedOpen(true); }} />
              </div>

              <details open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)} className="rounded-xl border bg-muted/20">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold marker:hidden">
                  <Settings2 className="size-4" /> Paramètres avancés
                </summary>
                <div className="grid gap-4 border-t p-4 sm:grid-cols-2 lg:grid-cols-3">
                  <Field label="Cadence (secondes)"><input className={inputClass} inputMode="decimal" value={cadence} onChange={(e) => setCadence(e.target.value)} /></Field>
                  <Field label="Frais PAPER"><input className={inputClass} inputMode="decimal" value={feeRate} onChange={(e) => setFeeRate(e.target.value)} /></Field>
                  <Field label="Spread (bps)"><input className={inputClass} inputMode="decimal" value={spreadBps} onChange={(e) => setSpreadBps(e.target.value)} /></Field>
                  <Field label="Slippage (bps)"><input className={inputClass} inputMode="decimal" value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)} /></Field>
                  <Field label="Timeout marché (s)"><input className={inputClass} inputMode="decimal" value={marketTimeout} onChange={(e) => setMarketTimeout(e.target.value)} /></Field>
                  <Field label="Timeout Agent (s)"><input className={inputClass} inputMode="decimal" value={agentTimeout} onChange={(e) => setAgentTimeout(e.target.value)} /></Field>
                  <Field label="Timeout Broker (s)"><input className={inputClass} inputMode="decimal" value={brokerTimeout} onChange={(e) => setBrokerTimeout(e.target.value)} /></Field>
                  {riskProfile === "custom" ? (
                    <>
                      <Field label="Ordre max (notional)"><input className={inputClass} value={customMaxOrder} onChange={(e) => setCustomMaxOrder(e.target.value)} /></Field>
                      <Field label="Whitelist Risk optionnelle" hint="Vide = la découverte Kraken reste autorisée dans le type de marché et l’actif de règlement configurés. Une liste non vide devient un garde-fou supplémentaire et doit inclure la paire de départ."><input className={inputClass} value={customAllowedPairs} onChange={(e) => setCustomAllowedPairs(e.target.value)} placeholder="BTC/USD, ETH/USD" /></Field>
                      {marketType === "PERPETUAL" ? (
                        <>
                          <Field label="Levier PAPER"><input className={inputClass} value={customLeverage} onChange={(e) => setCustomLeverage(e.target.value)} /></Field>
                          <Field label="Levier Risk max"><input className={inputClass} value={customMaxLeverage} onChange={(e) => setCustomMaxLeverage(e.target.value)} /></Field>
                          <Field label="Position dérivée max"><input className={inputClass} value={customPositionNotional} onChange={(e) => setCustomPositionNotional(e.target.value)} /></Field>
                          <Field label="Exposition dérivée totale max"><input className={inputClass} value={customTotalExposure} onChange={(e) => setCustomTotalExposure(e.target.value)} /></Field>
                          <Field label="Buffer liquidation"><input className={inputClass} value={customLiquidationBuffer} onChange={(e) => setCustomLiquidationBuffer(e.target.value)} /></Field>
                        </>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </details>
            </CardContent>
          </>
        ) : null}

        {step === 5 ? (
          <>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Sparkles className="size-4" /> Vérifier puis créer</CardTitle>
              <CardDescription>Aucun ordre Kraken n’est envoyé à cette étape. La création reste exclusivement PAPER.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <Field label="Nom de la configuration de test"><input className={inputClass} value={testName} onChange={(event) => setTestName(event.target.value)} /></Field>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Marché</p><p className="mt-1 font-semibold">{marketType}</p><p className="mt-1 text-xs text-muted-foreground">Découverte auto · secours {pairs}</p></div>
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Capital</p><p className="mt-1 font-semibold">{capital}</p><p className="mt-1 text-xs text-muted-foreground">PAPER</p></div>
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">IA</p><p className="mt-1 font-semibold">{model.replace("gpt-5.6-", "")}</p><p className="mt-1 text-xs text-muted-foreground">Agressivité {aggressiveness}/10</p></div>
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Risk</p><p className="mt-1 font-semibold">{riskProfile === "custom" ? "Personnalisé" : PROFILE_COPY[riskProfile].label}</p><p className="mt-1 text-xs text-muted-foreground">Backend autoritaire</p></div>
              </div>
              <div className="rounded-xl border bg-muted/20 p-4 text-sm">
                <p className="font-semibold">Découverte + pipeline canonique</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Kraken → présélection factuelle → watchlist du même Agent IA → cycle BUY/SELL/HOLD → Risk Engine déterministe → Broker PAPER. Une sélection de watchlist ne déclenche jamais directement une exécution.</p>
              </div>
              {plan.configuration ? (
                <details className="rounded-xl border px-4 py-3 text-xs">
                  <summary className="cursor-pointer font-semibold">Voir les valeurs canoniques envoyées au backend</summary>
                  <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 font-mono text-[11px] leading-relaxed">{JSON.stringify(plan.configuration, null, 2)}</pre>
                </details>
              ) : null}
              {control.engine?.status === "RUNNING" ? (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                  Une session est déjà en cours. Tu peux créer la configuration maintenant, mais il faut arrêter la session active avant de la démarrer.
                </p>
              ) : null}
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
                <Button variant="outline" onClick={() => void create(false)} disabled={busy || !plan.configuration}>
                  <Save className="size-4" /> Créer le test
                </Button>
                <Button onClick={() => void create(true)} disabled={busy || !plan.configuration || control.engine?.status === "RUNNING"}>
                  <Play className="size-4" /> Créer et démarrer
                </Button>
              </div>
            </CardContent>
          </>
        ) : null}
      </Card>

      {(validationError || (step === 5 && plan.error)) ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          {validationError ?? plan.error}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <Button variant="outline" onClick={() => setStep((current) => Math.max(1, current - 1) as WizardStep)} disabled={step === 1 || busy}>
          <ChevronLeft className="size-4" /> Retour
        </Button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge tone="info">PAPER</Badge>
          <span>Étape {step}/5</span>
        </div>
        <Button onClick={nextStep} disabled={step === 5 || busy}>
          Continuer <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
