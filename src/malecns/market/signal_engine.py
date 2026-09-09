"""Convert indexed Uniswap observations into physical habitat signals."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any

from .graph_client import GraphClient


@dataclass(frozen=True)
class PhysicalHabitatState:
    id: str
    label: str
    physical_radius_m: float
    resource_pile_radius_m: float
    visual_motion_intensity: float
    brightness: float
    particle_activity: float
    chaos: float
    attractive_odor: float
    aversive_danger: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "physicalRadiusM": self.physical_radius_m,
            "resourcePileRadiusM": self.resource_pile_radius_m,
            "visualMotionIntensity": self.visual_motion_intensity,
            "brightness": self.brightness,
            "particleActivity": self.particle_activity,
            "chaos": self.chaos,
            "attractiveOdor": self.attractive_odor,
            "aversiveDanger": self.aversive_danger,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    status: str
    observed_at_ms: int
    habitats: tuple[PhysicalHabitatState, ...]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": "graph-uniswap",
            "status": self.status,
            "observedAtMs": self.observed_at_ms,
            "habitats": [habitat.as_dict() for habitat in self.habitats],
            "rawMarketFieldsForwardedToFly": False,
        }
        if self.error:
            payload["error"] = self.error
        return payload


class MarketSignalEngine:
    """Poll configured pools with a deterministic, documented proxy mapping."""

    def __init__(self, graph: GraphClient, habitats: list[dict[str, Any]], *, poll_seconds: float = 15.0) -> None:
        self.graph = graph
        self.habitat_configs = habitats
        self.poll_seconds = poll_seconds
        self._last_poll = 0.0
        self._cached: dict[str, Any] | None = None

    @classmethod
    def from_env(cls) -> "MarketSignalEngine | None":
        graph = GraphClient.from_env()
        raw_habitats = os.getenv("NEUROSWARM_MARKET_HABITATS", "").strip()
        if graph is None or not raw_habitats:
            return None
        try:
            habitats = json.loads(raw_habitats)
        except json.JSONDecodeError as exc:
            raise ValueError("NEUROSWARM_MARKET_HABITATS must be valid JSON") from exc
        if not isinstance(habitats, list) or not all(isinstance(item, dict) for item in habitats):
            raise ValueError("NEUROSWARM_MARKET_HABITATS must be a JSON list of objects")
        return cls(graph, habitats, poll_seconds=float(os.getenv("NEUROSWARM_MARKET_POLL_SECONDS", "15")))

    def snapshot_if_due(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force and self._cached is not None and now - self._last_poll < self.poll_seconds:
            return self._cached
        try:
            habitats = tuple(self._read_habitat(config) for config in self.habitat_configs)
            snapshot = MarketSnapshot("ok", int(time.time() * 1000), habitats)
        except Exception as exc:
            snapshot = MarketSnapshot("error", int(time.time() * 1000), tuple(), str(exc))
        self._last_poll = now
        self._cached = snapshot.as_dict()
        return self._cached

    def _read_habitat(self, config: dict[str, Any]) -> PhysicalHabitatState:
        pool_id = str(config.get("poolId", "")).strip()
        habitat_id = str(config.get("id", "")).strip()
        label = str(config.get("label", habitat_id)).strip()
        if not habitat_id or not pool_id:
            raise ValueError("each market habitat requires id and poolId")
        swaps = self.graph.recent_swaps(pool_id, first=100)
        pool = self.graph.pool_state(pool_id) or {}
        activity = _clip(len(swaps) / 50.0)
        tvl = _number(pool.get("totalValueLockedUSD"))
        liquidity = _clip(tvl / 1_000_000.0)
        signed_flow = sum(_number(swap.get("amount0")) for swap in swaps)
        absolute_flow = sum(abs(_number(swap.get("amount0"))) for swap in swaps)
        flow = math.tanh(signed_flow / absolute_flow) if absolute_flow else 0.0
        volatility = _clip(abs(flow) * 0.7 + activity * 0.3)
        social = activity
        risk = _clip(volatility * 0.8 + (1.0 - liquidity) * 0.2)
        stable = _clip(0.2 + liquidity * 0.8)
        return PhysicalHabitatState(
            id=habitat_id,
            label=label,
            physical_radius_m=0.09 + liquidity * 0.13,
            resource_pile_radius_m=0.045 + activity * 0.045,
            visual_motion_intensity=_clip(activity * 0.72 + abs(flow) * 0.18 + social * 0.1),
            brightness=_clip(0.16 + activity * 0.42 + social * 0.18),
            particle_activity=_clip(activity * 0.7 + social * 0.2 + volatility * 0.1),
            chaos=_clip(volatility * 0.6 + risk * 0.3 + (1.0 - stable) * 0.1),
            attractive_odor=_clip(activity * 0.55 + liquidity * 0.25 + max(0.0, flow) * 0.2),
            aversive_danger=_clip(risk * 0.75 + volatility * 0.15 + (1.0 - stable) * 0.1),
        )


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
