"""DexScreener market discovery, eligibility, and locked arena rounds.

Discovery answers only: "which markets are available to put in the arena?"
It does not answer whether a market is attractive, safe, profitable, or where
a fly should move. The selected candidates are later observed by a deeper
provider such as The Graph and converted into physical habitat signals.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Iterable, Mapping

from .dexscreener_client import DexScreenerClient
from .models import MarketCandidate, MarketIdentity


@dataclass(frozen=True)
class MarketUniverse:
    core_markets: tuple[MarketCandidate, ...]
    recent_markets: tuple[MarketCandidate, ...]
    refreshed_at_ms: int

    @property
    def all_candidates(self) -> tuple[MarketCandidate, ...]:
        seen: set[str] = set()
        result: list[MarketCandidate] = []
        for candidate in (*self.core_markets, *self.recent_markets):
            if candidate.market_id in seen:
                continue
            seen.add(candidate.market_id)
            result.append(candidate)
        return tuple(result)

    def as_dict(self) -> dict[str, Any]:
        return {
            "coreCount": len(self.core_markets),
            "recentCount": len(self.recent_markets),
            "candidateCount": len(self.all_candidates),
            "refreshedAtMs": self.refreshed_at_ms,
            "coreMarkets": [candidate.as_dict() for candidate in self.core_markets],
            "recentMarkets": [candidate.as_dict() for candidate in self.recent_markets],
        }


@dataclass
class DexScreenerUniverseProvider:
    """Build a bounded market universe from documented DexScreener feeds."""

    client: DexScreenerClient
    # Keep Ethereum for continuity, while including the chains used by the
    # deployed demo. An empty dex_ids tuple means all DEXs on those chains.
    chains: tuple[str, ...] = ("ethereum", "base", "robinhood")
    dex_ids: tuple[str, ...] = ()
    core_target: int = 100
    recent_target: int = 20
    profile_limit: int = 60
    seed_tokens: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    pool_bootstrap: Callable[..., list[dict[str, Any]]] | None = None
    last_bootstrap_error: str | None = field(default=None, init=False)

    def refresh(self, *, now_ms: int | None = None, force: bool = False) -> MarketUniverse:
        observed_at_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        allowed_chains = {_norm(value) for value in self.chains if str(value).strip()}
        allowed_dexes = {_norm(value) for value in self.dex_ids if str(value).strip()}

        latest_profiles = self.client.latest_token_profiles(force=force)
        recent_profiles = self.client.recent_token_profiles(force=force)
        core_addresses = _profile_addresses(latest_profiles, allowed_chains, self.profile_limit)
        recent_addresses = _profile_addresses(recent_profiles, allowed_chains, self.profile_limit)
        for chain_id, addresses in self.seed_tokens.items():
            chain = _norm(chain_id)
            if chain in allowed_chains:
                core_addresses.setdefault(chain, []).extend(addresses)

        profile_class: dict[tuple[str, str], str] = {}
        for chain, addresses in core_addresses.items():
            for address in addresses:
                profile_class[(chain, _norm(address))] = "core"
        for chain, addresses in recent_addresses.items():
            for address in addresses:
                profile_class.setdefault((chain, _norm(address)), "recent")

        core_pairs: dict[str, MarketCandidate] = {}
        recent_pairs: dict[str, MarketCandidate] = {}

        # DexScreener's profile feeds are intentionally not treated as an
        # exhaustive Ethereum pool index. When a configured Graph observer can
        # enumerate pools, use it only to discover pair addresses, then ask
        # DexScreener for the normalized pair metadata.
        self.last_bootstrap_error = None
        if self.pool_bootstrap is not None:
            try:
                bootstrap_pools = self.pool_bootstrap(first=max(1, min(self.core_target, 100)))
            except Exception as exc:
                bootstrap_pools = []
                self.last_bootstrap_error = str(exc)
            default_chain = next(iter(sorted(allowed_chains)), "ethereum")
            for pool in bootstrap_pools:
                if not isinstance(pool, Mapping):
                    continue
                chain_id = _norm(pool.get("chainId") or default_chain)
                pair_address = _optional_norm(pool.get("pairAddress") or pool.get("id"))
                if chain_id not in allowed_chains or not pair_address:
                    continue
                try:
                    dex_pairs = self.client.pair(chain_id, pair_address, force=force)
                except Exception as exc:
                    self.last_bootstrap_error = str(exc)
                    continue
                for pair in dex_pairs:
                    candidate = candidate_from_pair(pair, observed_at_ms=observed_at_ms)
                    if candidate is None or (allowed_dexes and _norm(candidate.identity.dex_id) not in allowed_dexes):
                        continue
                    current = core_pairs.get(candidate.market_id)
                    if current is None or _candidate_quality(candidate) > _candidate_quality(current):
                        core_pairs[candidate.market_id] = candidate

        for chain_id in sorted(allowed_chains):
            addresses = _unique_addresses(
                [*core_addresses.get(chain_id, ()), *recent_addresses.get(chain_id, ())]
            )
            if not addresses:
                continue
            for pair in self.client.tokens(chain_id, addresses, force=force):
                candidate = candidate_from_pair(
                    pair,
                    profile_class=profile_class,
                    observed_at_ms=observed_at_ms,
                )
                if candidate is None or (allowed_dexes and _norm(candidate.identity.dex_id) not in allowed_dexes):
                    continue
                target = core_pairs if _candidate_class(candidate, profile_class) == "core" else recent_pairs
                current = target.get(candidate.market_id)
                if current is None or _candidate_quality(candidate) > _candidate_quality(current):
                    target[candidate.market_id] = candidate

        core = tuple(sorted(core_pairs.values(), key=_universe_sort_key)[: max(0, self.core_target)])
        recent = tuple(sorted(recent_pairs.values(), key=_universe_sort_key)[: max(0, self.recent_target)])
        return MarketUniverse(core, recent, observed_at_ms)


@dataclass(frozen=True)
class MarketEligibility:
    """Quality and scope checks used before selecting active arena markets."""

    chains: tuple[str, ...] = ("ethereum", "base", "robinhood")
    dex_ids: tuple[str, ...] = ()
    min_liquidity_usd: float = 100_000.0
    min_volume_24h_usd: float = 100_000.0
    min_pair_age_seconds: int = 3_600

    def accepts(self, candidate: MarketCandidate, *, now_ms: int | None = None) -> bool:
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        if _norm(candidate.identity.chain_id) not in {_norm(value) for value in self.chains}:
            return False
        # DEX filtering is optional so Base and Robinhood can use their native
        # venues without being silently removed by an Ethereum-only list.
        if self.dex_ids and _norm(candidate.identity.dex_id) not in {_norm(value) for value in self.dex_ids}:
            return False
        if not candidate.identity.pair_address or not candidate.represented_token_address:
            return False
        if candidate.liquidity_usd < self.min_liquidity_usd:
            return False
        if (candidate.volume_24h_usd or 0.0) < self.min_volume_24h_usd:
            return False
        if candidate.pair_created_at_ms is None:
            return False
        age_seconds = max(0.0, (current_ms - candidate.pair_created_at_ms) / 1000.0)
        return age_seconds >= self.min_pair_age_seconds


@dataclass(frozen=True)
class SelectedMarket:
    """Internal selection result; its score never enters TokenState or sensors."""

    candidate: MarketCandidate
    discovery_score: float


@dataclass
class MarketSelector:
    eligibility: MarketEligibility = field(default_factory=MarketEligibility)
    # Kept as active_count for compatibility with existing callers; it is the
    # number of markets sent to a deep observer, not the physical world size.
    active_count: int = 12
    world_capacity: int = 128

    def eligible(self, universe: MarketUniverse, *, now_ms: int | None = None) -> tuple[MarketCandidate, ...]:
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        candidates = [candidate for candidate in universe.all_candidates if self.eligibility.accepts(candidate, now_ms=current_ms)]
        # One representative pair per chain-aware token identity prevents the
        # arena from filling with several pools for the same token.
        by_token: dict[str, MarketCandidate] = {}
        for candidate in candidates:
            previous = by_token.get(candidate.token_id)
            if previous is None or _candidate_quality(candidate) > _candidate_quality(previous):
                by_token[candidate.token_id] = candidate
        return tuple(sorted(by_token.values(), key=lambda item: item.market_id))

    def select(self, universe: MarketUniverse, *, now_ms: int | None = None) -> tuple[SelectedMarket, ...]:
        return self._ranked(universe, now_ms=now_ms)[: max(0, self.active_count)]

    def select_world(self, universe: MarketUniverse, *, now_ms: int | None = None) -> tuple[MarketCandidate, ...]:
        return tuple(item.candidate for item in self._ranked(universe, now_ms=now_ms)[: max(0, self.world_capacity)])

    def _ranked(self, universe: MarketUniverse, *, now_ms: int | None = None) -> list[SelectedMarket]:
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        scored = [
            SelectedMarket(candidate, _discovery_score(candidate))
            for candidate in self.eligible(universe, now_ms=current_ms)
        ]
        scored.sort(key=lambda item: (-item.discovery_score, item.candidate.market_id))
        return scored


@dataclass(frozen=True)
class MarketRound:
    round_number: int
    started_at_ms: int
    expires_at_ms: int
    markets: tuple[MarketCandidate, ...]
    deep_markets: tuple[MarketCandidate, ...] = ()

    def is_active(self, now_ms: int) -> bool:
        return int(now_ms) < self.expires_at_ms

    def as_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_number,
            "startedAtMs": self.started_at_ms,
            "expiresAtMs": self.expires_at_ms,
            "markets": [market.as_dict() for market in self.markets],
            "deepMarkets": [market.as_dict() for market in self.deep_markets],
        }


@dataclass
class MarketRoundManager:
    selector: MarketSelector
    round_seconds: int = 600
    _current: MarketRound | None = field(default=None, init=False, repr=False)
    _round_counter: int = field(default=0, init=False, repr=False)

    def active_round(self, universe: MarketUniverse, *, now_ms: int | None = None, force: bool = False) -> MarketRound:
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        if not force and self._current is not None and self._current.is_active(current_ms):
            return self._current
        deep_selected = self.selector.select(universe, now_ms=current_ms)
        world_selected = self.selector.select_world(universe, now_ms=current_ms)
        self._round_counter += 1
        duration_ms = max(1, int(self.round_seconds)) * 1000
        self._current = MarketRound(
            round_number=self._round_counter,
            started_at_ms=current_ms,
            expires_at_ms=current_ms + duration_ms,
            markets=tuple(world_selected),
            deep_markets=tuple(item.candidate for item in deep_selected),
        )
        return self._current


@dataclass
class DexScreenerMarketDiscovery:
    """Cached universe + locked selection facade used by the market engine."""

    universe_provider: DexScreenerUniverseProvider
    rounds: MarketRoundManager
    refresh_seconds: float = 300.0
    cache: Any | None = None
    _universe: MarketUniverse | None = field(default=None, init=False, repr=False)
    _last_refresh_monotonic: float = field(default=0.0, init=False, repr=False)
    _last_cached_round_started_ms: int | None = field(default=None, init=False, repr=False)
    last_error: str | None = field(default=None, init=False)

    @classmethod
    def from_env(cls, *, graph_client: Any | None = None) -> "DexScreenerMarketDiscovery | None":
        enabled = os.getenv("NEUROSWARM_MARKET_DISCOVERY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return None
        chains = _csv(os.getenv("NEUROSWARM_MARKET_CHAINS", "ethereum,base,robinhood")) or ("ethereum", "base", "robinhood")
        configured_dex_ids = os.getenv("NEUROSWARM_MARKET_DEX_IDS", "").strip()
        dex_ids = _csv(configured_dex_ids) if configured_dex_ids else ()
        seeds = _seed_tokens(os.getenv("NEUROSWARM_MARKET_DISCOVERY_TOKEN_ADDRESSES", ""), chains[0])
        client = DexScreenerClient(
            base_url=os.getenv("DEXSCREENER_API_BASE_URL", "https://api.dexscreener.com").strip() or "https://api.dexscreener.com",
            timeout_seconds=float(os.getenv("DEXSCREENER_TIMEOUT_SECONDS", "10")),
            cache_ttl_seconds=float(os.getenv("DEXSCREENER_CACHE_TTL_SECONDS", "60")),
        )
        eligibility = MarketEligibility(
            chains=chains,
            dex_ids=dex_ids,
            min_liquidity_usd=float(os.getenv("NEUROSWARM_MARKET_MIN_LIQUIDITY_USD", "100000")),
            min_volume_24h_usd=float(os.getenv("NEUROSWARM_MARKET_MIN_VOLUME_24H_USD", "100000")),
            min_pair_age_seconds=int(os.getenv("NEUROSWARM_MARKET_MIN_PAIR_AGE_SECONDS", "3600")),
        )
        provider = DexScreenerUniverseProvider(
            client,
            chains=chains,
            dex_ids=dex_ids,
            core_target=int(os.getenv("NEUROSWARM_MARKET_CORE_TARGET", "100")),
            recent_target=int(os.getenv("NEUROSWARM_MARKET_RECENT_TARGET", "20")),
            profile_limit=int(os.getenv("NEUROSWARM_MARKET_PROFILE_LIMIT", "60")),
            seed_tokens=seeds,
            pool_bootstrap=graph_client.top_pools if graph_client is not None else None,
        )
        selector = MarketSelector(
            eligibility,
            active_count=int(os.getenv("NEUROSWARM_MARKET_DEEP_OBSERVER_COUNT", "12")),
            world_capacity=int(os.getenv("NEUROSWARM_MARKET_WORLD_CAPACITY", "128")),
        )
        from .supabase_cache import SupabaseMarketCache

        return cls(
            provider,
            MarketRoundManager(selector, round_seconds=int(os.getenv("NEUROSWARM_MARKET_ROUND_SECONDS", "600"))),
            refresh_seconds=float(os.getenv("NEUROSWARM_MARKET_CACHE_TTL_SECONDS", os.getenv("NEUROSWARM_MARKET_DISCOVERY_REFRESH_SECONDS", "300"))),
            cache=SupabaseMarketCache.from_env(),
        )

    def active_round(self, *, now_ms: int | None = None, force: bool = False) -> MarketRound:
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        now_monotonic = time.monotonic()
        if force or self._universe is None or now_monotonic - self._last_refresh_monotonic >= self.refresh_seconds:
            if not force and self._universe is None and self.cache is not None:
                try:
                    cached = self.cache.load_active(current_ms)
                except Exception as exc:
                    cached = None
                    self.last_error = f"cache read: {exc}"
                if cached is not None:
                    self._universe, cached_round = cached
                    self.rounds._current = cached_round
                    self.rounds._round_counter = max(self.rounds._round_counter, cached_round.round_number)
                    self._last_refresh_monotonic = now_monotonic
                    self._last_cached_round_started_ms = cached_round.started_at_ms
                    return cached_round
            try:
                self._universe = self.universe_provider.refresh(now_ms=current_ms, force=force)
                self._last_refresh_monotonic = now_monotonic
                self.last_error = self.universe_provider.last_bootstrap_error
            except Exception as exc:
                self.last_error = str(exc)
                if self._universe is None:
                    raise
        round_state = self.rounds.active_round(self._universe, now_ms=current_ms, force=force)
        if self.cache is not None and round_state.started_at_ms != self._last_cached_round_started_ms:
            try:
                self.cache.save(self._universe, round_state)
                self._last_cached_round_started_ms = round_state.started_at_ms
            except Exception as exc:
                # Persistence must never take the live market feed down.
                self.last_error = f"cache write: {exc}"
        return round_state

    def graph_habitat_configs(self, *, now_ms: int | None = None, force: bool = False) -> list[dict[str, Any]]:
        """Convert selected candidates to the existing GraphProvider contract."""

        return [
            self._config_for(candidate)
            for candidate in self.active_round(now_ms=now_ms, force=force).deep_markets
            if _norm(candidate.identity.chain_id) == "ethereum"
            and _norm(candidate.identity.dex_id) in {"uniswap", "uniswap-v3"}
        ]

    def world_habitat_configs(self, *, now_ms: int | None = None, force: bool = False) -> list[dict[str, Any]]:
        """Convert every physically present market to a lightweight config."""

        return [self._config_for(candidate) for candidate in self.active_round(now_ms=now_ms, force=force).markets]

    @staticmethod
    def _config_for(candidate: MarketCandidate) -> dict[str, Any]:
        label = candidate.base_token_symbol or candidate.base_token_name or candidate.market_id
        if candidate.base_token_name and candidate.base_token_symbol and candidate.base_token_name.lower() != candidate.base_token_symbol.lower():
            label = f"{candidate.base_token_symbol} · {candidate.base_token_name}"
        return {
            "id": candidate.market_id,
            "label": label,
            "marketName": candidate.base_token_name,
            "imageUrl": candidate.image_url,
            "poolId": candidate.identity.pair_address,
            "tokenAddress": candidate.represented_token_address,
            "chainId": candidate.identity.chain_id,
            "dexId": candidate.identity.dex_id,
            "pairAddress": candidate.identity.pair_address,
            "lightweight": True,
            "liquidityUsd": candidate.liquidity_usd,
            "volume5mUsd": candidate.volume_5m_usd,
            "volume1hUsd": candidate.volume_1h_usd,
            "volume24hUsd": candidate.volume_24h_usd,
            "buys5m": candidate.buys_5m,
            "sells5m": candidate.sells_5m,
        }

    def as_dict(self, *, now_ms: int | None = None) -> dict[str, Any]:
        round_state = self.active_round(now_ms=now_ms)
        return {
            "source": "dexscreener",
            "universe": self._universe.as_dict() if self._universe else None,
            "round": round_state.as_dict(),
            "lastError": self.last_error,
        }


def candidate_from_pair(
    pair: Mapping[str, Any],
    *,
    profile_class: Mapping[tuple[str, str], str] | None = None,
    observed_at_ms: int | None = None,
) -> MarketCandidate | None:
    """Normalize one DexScreener pair payload without adding derived bias."""

    chain_id = _norm(pair.get("chainId"))
    dex_id = _norm(pair.get("dexId"))
    pair_address = _norm(pair.get("pairAddress"))
    base = pair.get("baseToken") if isinstance(pair.get("baseToken"), Mapping) else {}
    quote = pair.get("quoteToken") if isinstance(pair.get("quoteToken"), Mapping) else {}
    base_address = _norm(base.get("address"))
    if not chain_id or not dex_id or not pair_address or not base_address:
        return None
    quote_address = _optional_norm(quote.get("address"))
    liquidity = pair.get("liquidity") if isinstance(pair.get("liquidity"), Mapping) else {}
    volume = pair.get("volume") if isinstance(pair.get("volume"), Mapping) else {}
    txns = pair.get("txns") if isinstance(pair.get("txns"), Mapping) else {}
    price_change = pair.get("priceChange") if isinstance(pair.get("priceChange"), Mapping) else {}
    info = pair.get("info") if isinstance(pair.get("info"), Mapping) else {}
    image_url = _optional_string(info.get("imageUrl")) or _optional_string(pair.get("imageUrl"))
    websites = _dict_tuple(info.get("websites"))
    socials = _dict_tuple(info.get("socials"))
    timestamp_ms = int(time.time() * 1000) if observed_at_ms is None else int(observed_at_ms)
    created_ms = _timestamp_ms(pair.get("pairCreatedAt"))
    provenance = (
        {
            "provider": "dexscreener",
            "endpoint": "/tokens/v1/{chainId}/{tokenAddresses}",
            "observedAtMs": timestamp_ms,
            "url": _optional_string(pair.get("url")),
        },
    )
    return MarketCandidate(
        identity=MarketIdentity(chain_id, dex_id, pair_address),
        base_token_address=base_address,
        base_token_symbol=_optional_string(base.get("symbol")) or "",
        base_token_name=_optional_string(base.get("name")) or "",
        quote_token_address=quote_address,
        quote_token_symbol=_optional_string(quote.get("symbol")),
        represented_token_address=base_address,
        liquidity_usd=_number(liquidity.get("usd")) or 0.0,
        volume_5m_usd=_optional_number(volume.get("m5")),
        volume_1h_usd=_optional_number(volume.get("h1")),
        volume_24h_usd=_optional_number(volume.get("h24")),
        buys_5m=_nested_int(txns, "m5", "buys"),
        sells_5m=_nested_int(txns, "m5", "sells"),
        buys_1h=_nested_int(txns, "h1", "buys"),
        sells_1h=_nested_int(txns, "h1", "sells"),
        price_change_5m=_optional_number(price_change.get("m5")),
        price_change_1h=_optional_number(price_change.get("h1")),
        price_change_24h=_optional_number(price_change.get("h24")),
        pair_created_at_ms=created_ms,
        image_url=image_url,
        websites=websites,
        socials=socials,
        source="dexscreener",
        provenance=provenance,
    )


def _profile_addresses(profiles: Iterable[Mapping[str, Any]], chains: set[str], limit: int) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for profile in profiles:
        chain_id = _norm(profile.get("chainId"))
        address = _optional_string(profile.get("tokenAddress"))
        if chain_id not in chains or not address:
            continue
        if len(result.get(chain_id, ())) >= max(0, limit):
            continue
        result.setdefault(chain_id, []).append(address)
    return result


def _candidate_class(candidate: MarketCandidate, profile_class: Mapping[tuple[str, str], str]) -> str:
    chain = candidate.identity.chain_id
    if profile_class.get((chain, candidate.base_token_address)) == "core":
        return "core"
    if profile_class.get((chain, candidate.quote_token_address or "")) == "core":
        return "core"
    if profile_class.get((chain, candidate.base_token_address)) == "recent":
        return "recent"
    return "recent"


def _candidate_quality(candidate: MarketCandidate) -> tuple[float, float, str]:
    return (candidate.liquidity_usd, candidate.volume_24h_usd or 0.0, candidate.market_id)


def _universe_sort_key(candidate: MarketCandidate) -> tuple[float, float, str]:
    return (-candidate.liquidity_usd, -(candidate.volume_24h_usd or 0.0), candidate.market_id)


def _discovery_score(candidate: MarketCandidate) -> float:
    """Rank market data for arena inclusion, never for fly attraction."""

    liquidity = math.tanh(max(0.0, candidate.liquidity_usd) / 1_000_000.0)
    volume = math.tanh(max(0.0, candidate.volume_24h_usd or 0.0) / 1_000_000.0)
    transactions = sum(value or 0 for value in (candidate.buys_1h, candidate.sells_1h))
    activity = math.tanh(max(0, transactions) / 200.0)
    movement = math.tanh(abs(candidate.price_change_1h or 0.0) / 10.0)
    return 0.40 * liquidity + 0.30 * volume + 0.20 * activity + 0.10 * movement


def _nested_int(value: Mapping[str, Any], outer: str, inner: str) -> int | None:
    child = value.get(outer)
    return _optional_int(child.get(inner)) if isinstance(child, Mapping) else None


def _dict_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _timestamp_ms(value: Any) -> int | None:
    number = _optional_number(value)
    if number is None or number <= 0:
        return None
    return int(number if number >= 1_000_000_000_000 else number * 1000)


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float:
    return _optional_number(value) or 0.0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_norm(value: Any) -> str | None:
    normalized = _norm(value)
    return normalized or None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _unique_addresses(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized.lower() not in seen:
            result.append(normalized)
            seen.add(normalized.lower())
    return result


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in str(value or "").split(",") if item.strip())


def _seed_tokens(value: str, default_chain: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for item in str(value or "").split(","):
        token = item.strip()
        if not token:
            continue
        if ":" in token:
            chain, address = token.split(":", 1)
        else:
            chain, address = default_chain, token
        result.setdefault(chain.strip().lower(), []).append(address.strip())
    return {chain: tuple(_unique_addresses(addresses)) for chain, addresses in result.items()}
