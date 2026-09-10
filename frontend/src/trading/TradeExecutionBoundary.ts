import type { BehaviorTradeIntent } from '../networking/protocol'

export type TradeExecutionMode = 'proposal-only' | 'wallet-ready'

export interface TradeProposal {
  intent: BehaviorTradeIntent
  status: 'proposal_only'
  executionMode: TradeExecutionMode
  reason: string
}

/**
 * The future custody seam for fly-generated proposals.
 *
 * This deliberately does not connect a wallet, request a quote, sign, or
 * broadcast. A later adapter can take the proposal through market-route
 * validation, RiskGuard, Uniswap calldata, and an explicitly approved Privy
 * signer without changing the biological observer.
 */
export class TradeExecutionBoundary {
  readonly mode: TradeExecutionMode = 'proposal-only'

  prepare(intent: BehaviorTradeIntent): TradeProposal {
    return {
      intent,
      status: 'proposal_only',
      executionMode: this.mode,
      reason: 'behavior event captured; wallet execution is not enabled',
    }
  }
}
