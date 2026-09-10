"""Provider-neutral market state and signal models.

Raw provider observations are kept separate from derived signals and from the
small physical habitat representation consumed by the browser. The holders,
security, social, and lore sections are intentionally explicit placeholders
until a provider supplies those facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .features.models import FinancialState


@dataclass(frozen=True)
class MarketIdentity:
    """Canonical identity for one chain-specific DEX pair."""

    chain_id: str
    dex_id: str
    pair_address: str

    @property
    def market_id(self) -> str:
        return f"{self.chain_id}:{self.pair_address}"

    def as_dict(self) -> dict[str, str]:
        return {
            "marketId": self.market_id,
            "chainId": self.chain_id,
            "dexId": self.dex_id,
            "pairAddress": self.pair_address,
        }


@dataclass(frozen=True)
class MarketCandidate:
    """A discovered market, before it is selected for an arena round.

    This model deliberately contains discovery facts and provenance only. It
    has no bullish flag, expected return, target position, or fly preference.
    """

    identity: MarketIdentity
    base_token_address: str
    base_token_symbol: str
    base_token_name: str
    quote_token_address: str | None
    quote_token_symbol: str | None
    represented_token_address: str
    liquidity_usd: float
    volume_5m_usd: float | None
    volume_1h_usd: float | None
    volume_24h_usd: float | None
    buys_5m: int | None
    sells_5m: int | None
    buys_1h: int | None
    sells_1h: int | None
    price_change_5m: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    pair_created_at_ms: int | None
    image_url: str | None
    websites: tuple[dict[str, Any], ...]
    socials: tuple[dict[str, Any], ...]
    source: str
    provenance: tuple[dict[str, Any], ...] = ()

    @property
    def market_id(self) -> str:
        return self.identity.market_id

    @property
    def token_id(self) -> str:
        return f"{self.identity.chain_id}:{self.represented_token_address}"

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity.as_dict(),
            "tokenId": self.token_id,
            "baseToken": {
                "address": self.base_token_address,
                "symbol": self.base_token_symbol,
                "name": self.base_token_name,
            },
            "quoteToken": {
                "address": self.quote_token_address,
                "symbol": self.quote_token_symbol,
            },
            "representedTokenAddress": self.represented_token_address,
            "liquidityUsd": self.liquidity_usd,
            "volume5mUsd": self.volume_5m_usd,
            "volume1hUsd": self.volume_1h_usd,
            "volume24hUsd": self.volume_24h_usd,
            "buys5m": self.buys_5m,
            "sells5m": self.sells_5m,
            "buys1h": self.buys_1h,
            "sells1h": self.sells_1h,
            "priceChange5m": self.price_change_5m,
            "priceChange1h": self.price_change_1h,
            "priceChange24h": self.price_change_24h,
            "pairCreatedAtMs": self.pair_created_at_ms,
            "imageUrl": self.image_url,
            "websites": list(self.websites),
            "socials": list(self.socials),
            "source": self.source,
            "provenance": list(self.provenance),
        }


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
    chain_id: str = "ethereum"
    dex_id: str = "uniswap"
    pair_address: str | None = None


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
    sellable: bool | None = None
    contract_verified: bool | None = None
    owner_control: str | None = None
    buy_tax_bps: int | None = None
    sell_tax_bps: int | None = None
    blacklist_mechanic: bool | None = None
    mint_capability: bool | None = None
    proxy: bool | None = None
    security_flags: tuple[str, ...] = ()


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
    chain_id: str = "ethereum"
    dex_id: str = "uniswap"
    pair_address: str | None = None
    financial: "FinancialState | None" = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tokenAddress": self.token_address,
            "poolId": self.pool_id,
            "chainId": self.chain_id,
            "dexId": self.dex_id,
            "pairAddress": self.pair_address or self.pool_id,
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
                "sellable": self.security.sellable,
                "contractVerified": self.security.contract_verified,
                "ownerControl": self.security.owner_control,
                "buyTaxBps": self.security.buy_tax_bps,
                "sellTaxBps": self.security.sell_tax_bps,
                "blacklistMechanic": self.security.blacklist_mechanic,
                "mintCapability": self.security.mint_capability,
                "proxy": self.security.proxy,
                "securityFlags": list(self.security.security_flags),
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
            "financial": self.financial.as_dict() if self.financial else None,
            "signals": [signal.as_dict() for signal in self.signals],
            "provenance": list(self.provenance),
        }
