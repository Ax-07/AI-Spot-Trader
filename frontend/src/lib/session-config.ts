import type {
  CampaignConfiguration,
  ExecutableMarketType,
  LlmModel,
  MarketDiscoveryPolicy,
  TradingStyle,
} from "@/lib/api/types";

export type SessionMarketSelectionMode = "AUTOMATIC_AI" | "MANUAL";
export type SessionRiskProfile = "prudent" | "balanced" | "aggressive" | "custom";

export const TRADING_STYLE_MAPPING_VERSION = "trading-style-map-v1" as const;

export const TRADING_STYLE_UI_METADATA = {
  SCALP: {
    label: "Scalping",
    detail: "Horizon court. Recherche d’opportunités rapides. Les coûts d’exécution ont une importance élevée.",
    timeframes: ["1m", "5m", "15m", "30m"],
    recommendedTradingCadenceSeconds: 60,
    recommendedWatchlistRefreshSeconds: 300,
  },
  SWING: {
    label: "Swing",
    detail: "Horizon de plusieurs heures à plusieurs jours. Recherche de mouvements plus larges.",
    timeframes: ["1h", "4h", "1d"],
    recommendedTradingCadenceSeconds: 900,
    recommendedWatchlistRefreshSeconds: 1800,
  },
} as const satisfies Record<
  TradingStyle,
  {
    label: string;
    detail: string;
    timeframes: readonly string[];
    recommendedTradingCadenceSeconds: number;
    recommendedWatchlistRefreshSeconds: number;
  }
>;

export const DEFAULT_MARKET_DISCOVERY_POLICY = {
  protocol_version: "market-discovery-v1",
  catalog_refresh_seconds: 900,
  watchlist_refresh_seconds: 900,
  refresh_timeout_seconds: 45,
  candidate_probe_limit: 24,
  candidate_limit: 12,
  watchlist_limit: 6,
  max_snapshot_age_seconds: 120,
  min_window_observations: 2,
  require_complete_window: false,
} as const;

export type SessionConfigurationInput = {
  marketType: ExecutableMarketType;
  marketSelectionMode: SessionMarketSelectionMode;
  pairs: string;
  capital: string;
  model: LlmModel;
  aggressiveness: number;
  tradingStyle: TradingStyle | null;
  riskProfile: SessionRiskProfile;
  cadence: string;
  feeRate: string;
  spreadBps: string;
  slippageBps: string;
  customMaxOrder: string;
  customLeverage: string;
  customMaxLeverage: string;
  customPositionNotional: string;
  customTotalExposure: string;
  customLiquidationBuffer: string;
  customAllowedPairs: string;
  marketTimeout: string;
  agentTimeout: string;
  brokerTimeout: string;
  discovery: Omit<MarketDiscoveryPolicy, "protocol_version" | "market_types">;
};

export function tradingStyleRecommendations(style: TradingStyle) {
  const metadata = TRADING_STYLE_UI_METADATA[style];
  return {
    tradingCadenceSeconds: metadata.recommendedTradingCadenceSeconds,
    watchlistRefreshSeconds: metadata.recommendedWatchlistRefreshSeconds,
  };
}

export function initialSessionStyleValues(
  configuration: CampaignConfiguration | null,
  editing: boolean,
) {
  const tradingStyle = configuration?.trading_style ?? (editing ? null : "SCALP");
  const recommendations = tradingStyle ? tradingStyleRecommendations(tradingStyle) : null;

  return {
    tradingStyle,
    tradingCadenceSeconds:
      configuration?.trading_cadence_seconds ?? recommendations?.tradingCadenceSeconds ?? 30,
    watchlistRefreshSeconds:
      configuration?.market_discovery?.watchlist_refresh_seconds ??
      recommendations?.watchlistRefreshSeconds ??
      DEFAULT_MARKET_DISCOVERY_POLICY.watchlist_refresh_seconds,
  };
}

function roundDecimal(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return String(Math.round(value * 100_000_000) / 100_000_000);
}

export function parseSessionMarkets(value: string, marketType: ExecutableMarketType) {
  const symbols = Array.from(
    new Set(
      value
        .split(/[\n,;]/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
  if (!symbols.length) throw new Error("Ajoute au moins une paire, par exemple BTC/USD.");
  const quotes = new Set<string>();
  for (const symbol of symbols) {
    const parts = symbol.split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new Error(`Paire invalide : ${symbol}. Utilise le format BASE/QUOTE.`);
    }
    quotes.add(parts[1]);
  }
  if (quotes.size !== 1) {
    throw new Error("Toutes les paires doivent utiliser le même actif de règlement.");
  }
  return {
    settlementAsset: Array.from(quotes)[0],
    symbols,
    markets: symbols.map((symbol) => ({ symbol, market_type: marketType })),
  };
}

export function profileRisk(
  profile: Exclude<SessionRiskProfile, "custom">,
  capital: number,
  marketType: ExecutableMarketType,
) {
  const values = {
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
    maxOrderNotional: roundDecimal(capital * values.orderFraction),
    derivativeLeverage: marketType === "PERPETUAL" ? values.leverage : "1",
    maxDerivativeLeverage: marketType === "PERPETUAL" ? values.leverage : "1",
    maxDerivativePositionNotional:
      marketType === "PERPETUAL" ? roundDecimal(capital * values.positionFraction) : null,
    maxTotalDerivativeExposure:
      marketType === "PERPETUAL" ? roundDecimal(capital * values.totalFraction) : null,
    liquidationBuffer: values.buffer,
  };
}

function decimalValuesEqual(left: string | null, right: string | null): boolean {
  if (left === null || right === null) return left === right;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  return Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftNumber === rightNumber;
}

export function inferSessionRiskProfile(configuration: CampaignConfiguration): SessionRiskProfile {
  const capital = Number(configuration.paper_initial_capital);
  const marketType = configuration.paper_executable_markets[0]?.market_type;
  if (!Number.isFinite(capital) || capital <= 0 || !marketType) return "custom";

  const profiles = ["prudent", "balanced", "aggressive"] as const;
  for (const profile of profiles) {
    const expected = profileRisk(profile, capital, marketType);
    if (
      decimalValuesEqual(configuration.risk_max_order_notional, expected.maxOrderNotional) &&
      decimalValuesEqual(configuration.paper_derivative_leverage, expected.derivativeLeverage) &&
      decimalValuesEqual(
        configuration.risk_max_derivative_leverage,
        expected.maxDerivativeLeverage,
      ) &&
      decimalValuesEqual(
        configuration.risk_max_derivative_position_notional,
        expected.maxDerivativePositionNotional,
      ) &&
      decimalValuesEqual(
        configuration.risk_max_total_derivative_exposure,
        expected.maxTotalDerivativeExposure,
      ) &&
      decimalValuesEqual(
        configuration.risk_derivative_liquidation_buffer_ratio,
        expected.liquidationBuffer,
      )
    ) {
      return profile;
    }
  }
  return "custom";
}

function splitPairs(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\n,;]/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function positiveNumber(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${label} doit être strictement positif.`);
  return parsed;
}

export function buildSessionCampaignConfiguration(input: SessionConfigurationInput): CampaignConfiguration {
  const capital = positiveNumber(input.capital, "Le capital PAPER");
  const marketPlan = parseSessionMarkets(input.pairs, input.marketType);
  const risk = input.riskProfile === "custom"
    ? {
        maxOrderNotional: input.customMaxOrder.trim(),
        derivativeLeverage: input.marketType === "PERPETUAL" ? input.customLeverage.trim() : "1",
        maxDerivativeLeverage: input.marketType === "PERPETUAL" ? input.customMaxLeverage.trim() : "1",
        maxDerivativePositionNotional:
          input.marketType === "PERPETUAL" ? input.customPositionNotional.trim() || null : null,
        maxTotalDerivativeExposure:
          input.marketType === "PERPETUAL" ? input.customTotalExposure.trim() || null : null,
        liquidationBuffer: input.customLiquidationBuffer.trim(),
      }
    : profileRisk(input.riskProfile, capital, input.marketType);

  if (!risk.maxOrderNotional) throw new Error("Le plafond par ordre est obligatoire.");
  const cadence = positiveNumber(input.cadence, "La cadence stratégique");
  const marketTimeout = positiveNumber(input.marketTimeout, "Le timeout marché");
  const agentTimeout = positiveNumber(input.agentTimeout, "Le timeout Agent");
  const brokerTimeout = positiveNumber(input.brokerTimeout, "Le timeout Broker");

  const customAllowed = splitPairs(input.customAllowedPairs);
  const riskAllowedPairs = input.marketSelectionMode === "MANUAL"
    ? marketPlan.symbols
    : customAllowed.length
      ? customAllowed
      : null;

  const discovery: MarketDiscoveryPolicy | null = input.marketSelectionMode === "AUTOMATIC_AI"
    ? {
        protocol_version: "market-discovery-v1",
        market_types: [input.marketType],
        ...input.discovery,
      }
    : null;

  const tradingStyle = input.tradingStyle === null
    ? {}
    : {
        trading_style: input.tradingStyle,
        trading_style_mapping_version: TRADING_STYLE_MAPPING_VERSION,
      };

  return {
    configuration_version: "paper-control-plane-config-v1",
    llm_model: input.model,
    aggressiveness: input.aggressiveness,
    trading_cadence_seconds: cadence,
    ...tradingStyle,
    paper_initial_capital: input.capital.trim(),
    paper_settlement_asset: marketPlan.settlementAsset,
    paper_executable_markets: marketPlan.markets,
    market_discovery: discovery,
    paper_fee_rate: input.feeRate.trim(),
    paper_spread_bps: input.spreadBps.trim(),
    paper_slippage_bps: input.slippageBps.trim(),
    paper_derivative_leverage: risk.derivativeLeverage,
    paper_derivative_margin_mode: "ISOLATED",
    risk_max_order_notional: risk.maxOrderNotional,
    risk_allowed_pairs: riskAllowedPairs,
    risk_allow_quantity_reduction: true,
    risk_max_derivative_leverage: risk.maxDerivativeLeverage,
    risk_max_derivative_position_notional: risk.maxDerivativePositionNotional,
    risk_max_total_derivative_exposure: risk.maxTotalDerivativeExposure,
    risk_derivative_liquidation_buffer_ratio: risk.liquidationBuffer,
    cycle_market_timeout_seconds: marketTimeout,
    cycle_agent_timeout_seconds: agentTimeout,
    cycle_broker_timeout_seconds: brokerTimeout,
  };
}

export function sessionStatusLabel(status: string): string {
  if (status === "DRAFT") return "Brouillon";
  if (status === "READY") return "Prête";
  if (status === "RUNNING") return "En cours";
  if (status === "STOPPED") return "Arrêtée";
  if (status === "RESUMABLE") return "À reprendre";
  if (status === "ARCHIVED") return "Archivée";
  return status;
}
