"""Provider-neutral market state and signal models.

Raw provider observations are kept separate from derived signals and from the
small physical habitat representation consumed by the browser. The holders,
security, social, and lore sections are intentionally explicit placeholders
until a provider supplies those facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawSwapObservation:
    swap_id: str
    timestamp_s: int
    amount0: float
    amount1: float
    amount_usd: float
    token0_address: str
    token1_address: str
    transaction_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawTokenObservation:
    provider: str
    token_id: str
    token_address: str
    pool_id: str
    label: str
    observed_at_ms: int
    pool: dict[str, Any]
    swaps: tuple[RawSwapObservation, ...]


@dataclass(frozen=True)
class Signal:
    name: str
    value: Any
    normalized: float
    importance: float
    valence: float
    confidence: float
    freshness: float
    source: str
    observed_at_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "normalized": self.normalized,
            "importance": self.importance,
            "valence": self.valence,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "source": self.source,
            "observedAtMs": self.observed_at_ms,
        }


@dataclass(frozen=True)
class MarketState:
    price_in_pair: float | None = None
    volume_5m_usd: float = 0.0
    volume_15m_usd: float = 0.0
    volume_1h_usd: float = 0.0


@dataclass(frozen=True)
class FlowState:
    buy_count_5m: int = 0
    sell_count_5m: int = 0
    buy_usd_5m: float = 0.0
    sell_usd_5m: float = 0.0
    flow_imbalance: float = 0.0
    tx_velocity_5m: float = 0.0
    tx_acceleration: float = 0.0


@dataclass(frozen=True)
class LiquidityState:
    liquidity_usd: float = 0.0
    liquidity_delta_usd: float | None = None
    volume_liquidity_ratio_1h: float = 0.0


@dataclass(frozen=True)
class HoldersState:
    status: str = "unavailable"
    holder_count: int | None = None
    growth_24h: float | None = None
    top10_concentration: float | None = None


@dataclass(frozen=True)
class SecurityState:
    status: str = "unavailable"
    honeypot: bool | None = None
    contract_verified: bool | None = None
    owner_control: str | None = None


@dataclass(frozen=True)
class SocialState:
    status: str = "unavailable"
    mentions: int | None = None
    sentiment: float | None = None


@dataclass(frozen=True)
class LoreState:
    status: str = "unavailable"
    catalysts: tuple[str, ...] = ()


@dataclass(frozen=True)
class TokenState:
    id: str
    label: str
    token_address: str
    pool_id: str
    observed_at_ms: int
    market: MarketState
    flow: FlowState
    liquidity: LiquidityState
    holders: HoldersState = field(default_factory=HoldersState)
    security: SecurityState = field(default_factory=SecurityState)
    social: SocialState = field(default_factory=SocialState)
    lore: LoreState = field(default_factory=LoreState)
    signals: tuple[Signal, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tokenAddress": self.token_address,
            "poolId": self.pool_id,
            "observedAtMs": self.observed_at_ms,
            "market": {
                "priceInPair": self.market.price_in_pair,
                "volume5mUsd": self.market.volume_5m_usd,
                "volume15mUsd": self.market.volume_15m_usd,
                "volume1hUsd": self.market.volume_1h_usd,
            },
            "flow": {
                "buyCount5m": self.flow.buy_count_5m,
                "sellCount5m": self.flow.sell_count_5m,
                "buyUsd5m": self.flow.buy_usd_5m,
                "sellUsd5m": self.flow.sell_usd_5m,
                "flowImbalance": self.flow.flow_imbalance,
                "txVelocity5m": self.flow.tx_velocity_5m,
                "txAcceleration": self.flow.tx_acceleration,
            },
            "liquidity": {
                "liquidityUsd": self.liquidity.liquidity_usd,
                "liquidityDeltaUsd": self.liquidity.liquidity_delta_usd,
                "volumeLiquidityRatio1h": self.liquidity.volume_liquidity_ratio_1h,
            },
            "holders": {
                "status": self.holders.status,
                "holderCount": self.holders.holder_count,
                "growth24h": self.holders.growth_24h,
                "top10Concentration": self.holders.top10_concentration,
            },
            "security": {
                "status": self.security.status,
                "honeypot": self.security.honeypot,
                "contractVerified": self.security.contract_verified,
                "ownerControl": self.security.owner_control,
            },
            "social": {
                "status": self.social.status,
                "mentions": self.social.mentions,
                "sentiment": self.social.sentiment,
            },
            "lore": {
                "status": self.lore.status,
                "catalysts": list(self.lore.catalysts),
            },
            "signals": [signal.as_dict() for signal in self.signals],
            "provenance": list(self.provenance),
        }
