"""Translate provider-neutral token signals into physical habitat fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import Signal, TokenState


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
    signals: tuple[Signal, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()

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
            "signals": [signal.as_dict() for signal in self.signals],
            "provenance": list(self.provenance),
        }


class HabitatEncoder:
    """Map explicit signals to environmental proxies, never directly to motion."""

    def encode(self, state: TokenState, signals: Iterable[Signal] | None = None) -> PhysicalHabitatState:
        signal_list = tuple(signals if signals is not None else state.signals)
        activity = _signal(signal_list, "market.volume5mUsd")
        tx_velocity = _signal(signal_list, "flow.txVelocity5m")
        liquidity = _signal(signal_list, "liquidity.usd")
        flow = _signal(signal_list, "flow.imbalance")
        risk = _clip(0.55 * (1.0 - liquidity.normalized) + 0.45 * abs(flow.valence))
        activity_level = _clip(0.65 * activity.normalized + 0.35 * tx_velocity.normalized)
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
            signals=signal_list,
            provenance=state.provenance,
        )


def _signal(signals: tuple[Signal, ...], name: str) -> Signal:
    for signal in signals:
        if signal.name == name:
            return signal
    return Signal(name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "unavailable", 0)


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
