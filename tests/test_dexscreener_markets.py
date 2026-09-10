from __future__ import annotations

from urllib.parse import urlparse

from malecns.market.dexscreener_client import DexScreenerClient
from malecns.market.universe import (
    DexScreenerUniverseProvider,
    MarketEligibility,
    MarketRoundManager,
    MarketSelector,
    candidate_from_pair,
)


def _pair(address: str = "0xpair", *, token: str = "0xtoken", liquidity: float = 250_000) -> dict:
    return {
        "chainId": "ethereum",
        "dexId": "uniswap",
        "url": "https://dexscreener.com/ethereum/0xpair",
        "pairAddress": address,
        "baseToken": {"address": token, "name": "Example Token", "symbol": "EXM"},
        "quoteToken": {"address": "0xusdc", "name": "USD Coin", "symbol": "USDC"},
        "priceUsd": "1.25",
        "txns": {"m5": {"buys": 4, "sells": 2}, "h1": {"buys": 40, "sells": 20}},
        "volume": {"m5": 1200, "h1": 25_000, "h24": 300_000},
        "priceChange": {"m5": 0.5, "h1": 3.2, "h24": 4.1},
        "liquidity": {"usd": liquidity, "base": 1000, "quote": 1000},
        "pairCreatedAt": 1_700_000_000_000,
        "info": {"imageUrl": "https://example.test/exm.png", "websites": [{"url": "https://example.test"}], "socials": [{"type": "twitter", "url": "https://x.test/exm"}]},
    }


def test_dexscreener_client_batches_token_lookup_at_thirty_addresses():
    requested: list[str] = []

    def fetch(url: str, _timeout: float):
        path = urlparse(url).path
        requested.append(path)
        return [_pair(address=f"0xpair{len(requested)}")]

    client = DexScreenerClient(fetcher=fetch)
    pairs = client.tokens("ethereum", [f"0xtoken{index}" for index in range(31)])

    assert len(pairs) == 2
    assert requested[0] == "/tokens/v1/ethereum/" + ",".join(f"0xtoken{index}" for index in range(30))
    assert requested[1] == "/tokens/v1/ethereum/0xtoken30"


def test_candidate_normalizes_pair_identity_and_preserves_provider_fields():
    candidate = candidate_from_pair(_pair(), observed_at_ms=1_700_010_000_000)

    assert candidate is not None
    assert candidate.market_id == "ethereum:0xpair"
    assert candidate.token_id == "ethereum:0xtoken"
    assert candidate.identity.dex_id == "uniswap"
    assert candidate.liquidity_usd == 250_000
    assert candidate.volume_24h_usd == 300_000
    assert candidate.buys_1h == 40
    assert candidate.price_change_1h == 3.2
    assert candidate.image_url == "https://example.test/exm.png"
    assert candidate.as_dict()["marketId"] == "ethereum:0xpair"


def test_universe_uses_profiles_as_seed_universe_and_filters_dex():
    pair = _pair()

    def fetch(url: str, _timeout: float):
        path = urlparse(url).path
        if path == "/token-profiles/latest/v1":
            return [{"chainId": "ethereum", "tokenAddress": "0xtoken"}]
        if path == "/token-profiles/recent-updates/v1":
            return []
        if path.startswith("/tokens/v1/"):
            return [pair]
        raise AssertionError(path)

    provider = DexScreenerUniverseProvider(
        DexScreenerClient(fetcher=fetch),
        chains=("ethereum",),
        dex_ids=("uniswap",),
        core_target=100,
        recent_target=20,
    )
    universe = provider.refresh(now_ms=1_700_010_000_000)

    assert len(universe.core_markets) == 1
    assert universe.core_markets[0].market_id == "ethereum:0xpair"
    assert universe.recent_markets == ()
    assert universe.as_dict()["candidateCount"] == 1


def test_universe_accepts_native_base_venue_when_dex_filter_is_empty():
    pair = {**_pair(), "chainId": "base", "dexId": "aerodrome"}

    def fetch(url: str, _timeout: float):
        path = urlparse(url).path
        if path == "/token-profiles/latest/v1":
            return [{"chainId": "base", "tokenAddress": "0xtoken"}]
        if path == "/token-profiles/recent-updates/v1":
            return []
        if path.startswith("/tokens/v1/"):
            return [pair]
        raise AssertionError(path)

    provider = DexScreenerUniverseProvider(
        DexScreenerClient(fetcher=fetch),
        chains=("base", "robinhood"),
        dex_ids=(),
    )
    universe = provider.refresh(now_ms=1_700_010_000_000)

    assert len(universe.core_markets) == 1
    assert universe.core_markets[0].identity.chain_id == "base"
    assert universe.core_markets[0].identity.dex_id == "aerodrome"


def test_selector_filters_quality_and_round_manager_locks_selected_markets():
    good = candidate_from_pair(_pair("0xgood", liquidity=250_000), observed_at_ms=1_700_010_000_000)
    young = candidate_from_pair({**_pair("0xyoung"), "pairCreatedAt": 1_700_009_500_000}, observed_at_ms=1_700_010_000_000)
    assert good is not None and young is not None
    from malecns.market.universe import MarketUniverse

    universe = MarketUniverse((good,), (young,), 1_700_010_000_000)
    selector = MarketSelector(
        MarketEligibility(min_liquidity_usd=100_000, min_volume_24h_usd=100_000, min_pair_age_seconds=3_600),
        active_count=1,
    )
    manager = MarketRoundManager(selector, round_seconds=600)
    first = manager.active_round(universe, now_ms=1_700_010_000_000)
    same = manager.active_round(universe, now_ms=1_700_010_100_000)
    next_round = manager.active_round(universe, now_ms=1_700_010_600_001)

    assert [item.market_id for item in first.markets] == ["ethereum:0xgood"]
    assert same.round_number == first.round_number
    assert next_round.round_number != first.round_number
    assert next_round.markets[0].market_id == "ethereum:0xgood"

    selected = selector.select(universe, now_ms=1_700_010_000_000)[0]
    assert selected.discovery_score > 0
    assert "discoveryScore" not in selected.candidate.as_dict()


def test_round_separates_physical_world_capacity_from_deep_observers():
    first = candidate_from_pair(_pair("0xone", token="0xone-token"), observed_at_ms=1_700_010_000_000)
    second = candidate_from_pair(_pair("0xtwo", token="0xtwo-token", liquidity=150_000), observed_at_ms=1_700_010_000_000)
    assert first is not None and second is not None
    from malecns.market.universe import MarketUniverse

    universe = MarketUniverse((first, second), (), 1_700_010_000_000)
    selector = MarketSelector(
        MarketEligibility(min_liquidity_usd=100_000, min_volume_24h_usd=100_000, min_pair_age_seconds=3_600),
        active_count=1,
        world_capacity=2,
    )
    round_state = MarketRoundManager(selector, round_seconds=600).active_round(universe, now_ms=1_700_010_000_000)

    assert len(round_state.markets) == 2
    assert len(round_state.deep_markets) == 1
    assert round_state.deep_markets[0].market_id in {item.market_id for item in round_state.markets}
