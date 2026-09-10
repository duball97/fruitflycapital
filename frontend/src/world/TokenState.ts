export interface Signal {
  name: string
  value: number | string | null
  normalized: number
  importance: number
  valence: number
  confidence: number
  freshness: number
  source: string
  observedAtMs: number
}

export interface MarketState {
  priceInPair: number | null
  volume5mUsd: number
  volume15mUsd: number
  volume1hUsd: number
}

export interface FlowState {
  buyCount5m: number
  sellCount5m: number
  buyUsd5m: number
  sellUsd5m: number
  flowImbalance: number
  txVelocity5m: number
  txAcceleration: number
}

export interface LiquidityState {
  liquidityUsd: number
  liquidityDeltaUsd: number | null
  volumeLiquidityRatio1h: number
}

export interface HoldersState {
  status: 'unavailable' | 'available'
  holderCount: number | null
  growth24h: number | null
  top10Concentration: number | null
}

export interface SecurityState {
  status: 'unavailable' | 'available'
  honeypot: boolean | null
  contractVerified: boolean | null
  ownerControl: string | null
}

export interface SocialState {
  status: 'unavailable' | 'available'
  mentions: number | null
  sentiment: number | null
}

export interface LoreState {
  status: 'unavailable' | 'available'
  catalysts: string[]
}

/** The frontend copy of the provider-neutral token domain model. */
export interface TokenState {
  id: string
  label: string
  tokenAddress: string | null
  poolId: string | null
  chainId?: string
  dexId?: string
  pairAddress?: string | null
  observedAtMs: number
  market: MarketState
  flow: FlowState
  liquidity: LiquidityState
  holders: HoldersState
  security: SecurityState
  social: SocialState
  lore: LoreState
  signals: Signal[]
  provenance: Array<Record<string, unknown>>
}
