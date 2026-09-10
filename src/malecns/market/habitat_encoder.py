"""Translate provider-neutral token signals into physical habitat fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .features.factors import FinancialFactorEngine
from .features.sensory import MultidimensionalSensoryEncoder
from .models import FlowState, LiquidityState, MarketState, Signal, TokenState


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
    semantic_type: str = "market"
    signals: tuple[Signal, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()
    financial_trace: dict[str, Any] | None = None

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
            "semanticType": self.semantic_type,
            "signals": [signal.as_dict() for signal in self.signals],
            "provenance": list(self.provenance),
            "financialTrace": self.financial_trace,
        }


class HabitatEncoder:
    """Map explicit signals to environmental proxies, never directly to motion."""

    def __init__(self, encoding_mode: str = "financial-sensory-v1") -> None:
        if encoding_mode not in {"legacy", "financial-sensory-v1"}:
            raise ValueError("encoding_mode must be legacy or financial-sensory-v1")
        self.encoding_mode = encoding_mode
        self._factor_engine = FinancialFactorEngine()
        self._sensory_encoder = MultidimensionalSensoryEncoder.from_file()

    def encode(self, state: TokenState, signals: Iterable[Signal] | None = None) -> PhysicalHabitatState:
        signal_list = tuple(signals if signals is not None else state.signals)
        if self.encoding_mode == "financial-sensory-v1":
            financial = state.financial or self._factor_engine.evaluate(state)
            sensory = self._sensory_encoder.encode(financial)
            return PhysicalHabitatState(
                id=state.id,
                label=state.label,
                physical_radius_m=0.09 + sensory.resource * 0.13,
                resource_pile_radius_m=0.045 + sensory.resource * 0.045,
                visual_motion_intensity=sensory.motion,
                brightness=0.16 + sensory.light * 0.5,
                particle_activity=min(1.0, sensory.motion * 0.72 + sensory.resource * 0.28),
                chaos=sensory.chaos,
                attractive_odor=sensory.odor_a,
                aversive_danger=sensory.odor_b,
                semantic_type=_semantic_type(sensory.motion, sensory.resource, sensory.chaos),
                signals=signal_list,
                provenance=state.provenance,
                financial_trace=sensory.trace,
            )
        activity = _signal(signal_list, "market.volume5mUsd")
        tx_velocity = _signal(signal_list, "flow.txVelocity5m")
        liquidity = _signal(signal_list, "liquidity.usd")
        flow = _signal(signal_list, "flow.imbalance")
        risk = _clip(0.55 * (1.0 - liquidity.normalized) + 0.45 * abs(flow.valence))
        activity_level = _clip(0.65 * activity.normalized + 0.35 * tx_velocity.normalized)
        semantic_type = _semantic_type(activity_level, liquidity.normalized, risk)
        return PhysicalHabitatState(
            id=state.id,
            label=state.label,
            physical_radius_m=0.09 + liquidity.normalized * 0.13,
            resource_pile_radius_m=0.045 + activity_level * 0.045,
            visual_motion_intensity=_clip(activity_level * 0.8 + abs(flow.valence) * 0.2),
            brightness=_clip(0.16 + activity_level * 0.5),
            particle_activity=_clip(activity_level * 0.72 + tx_velocity.normalized * 0.28),
            chaos=risk,
            attractive_odor=_clip(0.65 * activity_level + 0.2 * liquidity.normalized + 0.15 * max(0.0, flow.valence)),
            aversive_danger=risk,
            semantic_type=semantic_type,
            signals=signal_list,
            provenance=state.provenance,
        )

    def encode_lightweight(self, config: dict[str, Any]) -> PhysicalHabitatState:
        """Encode DexScreener identity/metrics without a deep Graph query.

        This keeps every physically present market alive in the world while a
        smaller deep-observer tier receives swap-level observations.
        """
        if self.encoding_mode == "financial-sensory-v1":
            buys = int(config.get("buys5m") or 0)
            sells = int(config.get("sells5m") or 0)
            total = buys + sells
            buy_usd = float(config.get("buyUsd5m") or 0.0)
            sell_usd = float(config.get("sellUsd5m") or 0.0)
            imbalance = (buy_usd - sell_usd) / (buy_usd + sell_usd) if buy_usd + sell_usd else ((buys - sells) / total if total else 0.0)
            state = TokenState(
                id=str(config.get("id", "")),
                label=str(config.get("label", config.get("id", ""))),
                token_address=str(config.get("tokenAddress", "")),
                pool_id=str(config.get("poolId", config.get("id", ""))),
                observed_at_ms=int(config.get("observedAtMs") or 0),
                market=MarketState(
                    volume_5m_usd=float(config.get("volume5mUsd") or 0.0),
                    volume_1h_usd=float(config.get("volume1hUsd") or 0.0),
                ),
                flow=FlowState(
                    buy_count_5m=buys,
                    sell_count_5m=sells,
                    buy_usd_5m=buy_usd,
                    sell_usd_5m=sell_usd,
                    flow_imbalance=imbalance,
                    tx_velocity_5m=total / 5.0,
                ),
                liquidity=LiquidityState(liquidity_usd=float(config.get("liquidityUsd") or 0.0)),
                provenance=({"provider": "dexscreener", "marketId": config.get("id"), "lightweight": True},),
                chain_id=str(config.get("chainId", "ethereum")),
                dex_id=str(config.get("dexId", "unknown")),
                pair_address=str(config.get("pairAddress", config.get("poolId", ""))),
            )
            return self.encode(state)
        activity = _clip(float(config.get("volume5mUsd") or 0.0) / 10_000.0)
        transactions = float((config.get("buys5m") or 0) + (config.get("sells5m") or 0))
        tx_velocity = _clip(transactions / 10.0)
        liquidity = _clip(float(config.get("liquidityUsd") or 0.0) / 1_000_000.0)
        total = float((config.get("buys5m") or 0) + (config.get("sells5m") or 0))
        flow = 0.0 if total <= 0 else (float(config.get("buys5m") or 0) - float(config.get("sells5m") or 0)) / total
        risk = _clip(0.55 * (1.0 - liquidity) + 0.45 * abs(flow))
        activity_level = _clip(0.65 * activity + 0.35 * tx_velocity)
        return PhysicalHabitatState(
            id=str(config.get("id", "")),
            label=str(config.get("label", config.get("id", ""))),
            physical_radius_m=0.09 + liquidity * 0.13,
            resource_pile_radius_m=0.045 + activity_level * 0.045,
            visual_motion_intensity=_clip(activity_level * 0.8 + abs(flow) * 0.2),
            brightness=_clip(0.16 + activity_level * 0.5),
            particle_activity=_clip(activity_level * 0.72 + tx_velocity * 0.28),
            chaos=risk,
            attractive_odor=_clip(0.65 * activity_level + 0.2 * liquidity + 0.15 * max(0.0, flow)),
            aversive_danger=risk,
            semantic_type=_semantic_type(activity_level, liquidity, risk),
            provenance=({
                "provider": "dexscreener",
                "marketId": config.get("id"),
                "imageUrl": config.get("imageUrl"),
                "marketName": config.get("marketName"),
                "lightweight": True,
            },),
        )


def _signal(signals: tuple[Signal, ...], name: str) -> Signal:
    for signal in signals:
        if signal.name == name:
            return signal
    return Signal(name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "unavailable", 0)


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _semantic_type(activity: float, liquidity: float, risk: float) -> str:
    """Choose a visual metaphor from encoded signals, not a fly command."""
    if risk >= 0.62:
        return "rot"
    if activity < 0.28:
        return "trash"
    if liquidity >= 0.62:
        return "food"
    return "market"
