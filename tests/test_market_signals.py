from __future__ import annotations

import pytest

from malecns.market.habitat_encoder import HabitatEncoder
from malecns.market.models import RawSwapObservation
from malecns.market.providers import GraphProvider
from malecns.market.signal_engine import TokenSignalEngine


TOKEN0 = "0xaaa"
TOKEN1 = "0xbbb"


def _observation(token_address: str = TOKEN0):
    now = 10_000
    pool = {
        "id": "0xpool",
        "token0": {"id": TOKEN0, "symbol": "AAA"},
        "token1": {"id": TOKEN1, "symbol": "USDC"},
        "token0Price": "2.0",
        "token1Price": "0.5",
        "totalValueLockedUSD": "500000",
    }
    swaps = (
        RawSwapObservation("buy", now - 60, -10, 5, 100, TOKEN0, TOKEN1, "tx-buy"),
        RawSwapObservation("sell", now - 120, 10, -5, 200, TOKEN0, TOKEN1, "tx-sell"),
        RawSwapObservation("previous", now - 360, -1, 1, 50, TOKEN0, TOKEN1, "tx-previous"),
        RawSwapObservation("fifteen-a", now - 660, -2, 1, 300, TOKEN0, TOKEN1, "tx-15-a"),
        RawSwapObservation("fifteen-b", now - 700, 2, -1, 400, TOKEN0, TOKEN1, "tx-15-b"),
        RawSwapObservation("hour", now - 1900, -3, 1, 500, TOKEN0, TOKEN1, "tx-hour"),
    )
    from malecns.market.models import RawTokenObservation

    return RawTokenObservation("the-graph", "TOKEN", token_address, "0xpool", "TOKEN", now * 1000, pool, swaps)


def test_graph_provider_returns_raw_observations_and_requires_token_identity():
    class FakeGraph:
        def __init__(self):
            self.request = None

        def pool_state(self, pool_id):
            return _observation().pool

        def recent_swaps(self, pool_id, *, first, since_timestamp):
            self.request = (pool_id, first, since_timestamp)
            return []

    graph = FakeGraph()
    provider = GraphProvider(graph, lookback_seconds=3600, swap_limit=1000)
    observation = provider.observe(
        {"id": "TOKEN", "label": "TOKEN", "poolId": "0xPOOL", "tokenAddress": TOKEN0},
        now_s=10_000,
    )
    assert observation.provider == "the-graph"
    assert graph.request == ("0xpool", 1000, 6400)
    with pytest.raises(ValueError, match="tokenAddress"):
        provider.observe({"id": "TOKEN", "poolId": "0xPOOL"}, now_s=10_000)


def test_signal_engine_uses_5m_15m_and_1h_windows():
    state = TokenSignalEngine().build_state(_observation())

    assert state.market.volume_5m_usd == 300
    assert state.market.volume_15m_usd == 1_050
    assert state.market.volume_1h_usd == 1_550
    assert state.flow.buy_count_5m == 1
    assert state.flow.sell_count_5m == 1
    assert state.flow.buy_usd_5m == 100
    assert state.flow.sell_usd_5m == 200
    assert state.flow.flow_imbalance == pytest.approx(-1 / 3)
    assert state.flow.tx_velocity_5m == pytest.approx(0.4)
    assert state.flow.tx_acceleration == pytest.approx(0.2)
    assert state.liquidity.liquidity_usd == 500_000
    assert state.liquidity.liquidity_delta_usd is None
    assert state.liquidity.volume_liquidity_ratio_1h == pytest.approx(1_550 / 500_000)
    assert {signal.name for signal in state.signals} >= {
        "market.volume5mUsd",
        "market.volume15mUsd",
        "market.volume1hUsd",
        "flow.buyCount5m",
        "flow.sellCount5m",
        "flow.buyUsd5m",
        "flow.sellUsd5m",
        "flow.imbalance",
        "flow.txVelocity5m",
        "flow.txAcceleration",
        "liquidity.usd",
        "liquidity.deltaUsd",
        "liquidity.volumeLiquidityRatio1h",
    }


def test_buy_sell_is_relative_to_represented_token_not_always_amount0():
    token0_state = TokenSignalEngine().build_state(_observation(TOKEN0))
    token1_state = TokenSignalEngine().build_state(_observation(TOKEN1))

    assert token0_state.flow.buy_usd_5m == 100
    assert token0_state.flow.sell_usd_5m == 200
    assert token1_state.flow.buy_usd_5m == 200
    assert token1_state.flow.sell_usd_5m == 100


def test_liquidity_delta_is_computed_from_previous_snapshot():
    state = TokenSignalEngine().build_state(_observation(), previous_liquidity_usd=450_000)
    assert state.liquidity.liquidity_delta_usd == 50_000
    delta_signal = next(signal for signal in state.signals if signal.name == "liquidity.deltaUsd")
    assert delta_signal.value == 50_000
    assert delta_signal.confidence == 1.0


def test_habitat_encoder_receives_signals_and_preserves_provenance():
    state = TokenSignalEngine().build_state(_observation())
    habitat = HabitatEncoder().encode(state)
    assert habitat.id == "TOKEN"
    assert habitat.signals == state.signals
    assert habitat.provenance[0]["provider"] == "the-graph"
    assert 0 <= habitat.brightness <= 1
    assert 0 <= habitat.attractive_odor <= 1


def test_signal_wire_format_uses_frontend_timestamp_name():
    state = TokenSignalEngine().build_state(_observation())
    signal = state.signals[0]
    payload = state.as_dict()
    assert signal.as_dict()["observedAtMs"] == 10_000_000
    assert "observed_at_ms" not in signal.as_dict()
    assert payload["tokenAddress"] == TOKEN0
    assert payload["market"]["volume5mUsd"] == 300
    assert payload["flow"]["buyCount5m"] == 1
    assert payload["liquidity"]["liquidityUsd"] == 500_000
    assert payload["signals"][0]["observedAtMs"] == 10_000_000
