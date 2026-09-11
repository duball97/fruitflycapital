"""Server-owned swarm motion used by the autonomous fund loop.

The browser renders the world, but it must not be the clock that decides
whether a fly visited a habitat.  This module produces the same small body
telemetry contract consumed by :class:`SwarmObserver`, allowing the brain
server to keep making behavior decisions when no browser is connected.

This is intentionally a lightweight kinematic world.  The authoritative
financial boundary remains the autonomous runtime and its execution queue;
the server motion only supplies repeatable approach, dwell, and departure
episodes to the biological observer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .observer import FlyObservation, HabitatObservation


@dataclass
class _ServerFly:
    fly_id: str
    target_habitat_id: str | None = None
    phase: str = "approach"
    phase_started_ms: int = 0
    cycle: int = 0
    buy_sent: bool = False


class ServerSwarmRuntime:
    """Generate server-side fly observations without a browser producer."""

    def __init__(
        self,
        expected_agents: int,
        *,
        approach_seconds: float = 8.0,
        departure_seconds: float = 10.0,
        min_hold_seconds: float = 120.0,
    ) -> None:
        self.expected_agents = max(1, int(expected_agents))
        self.approach_ms = max(1_000, int(float(approach_seconds) * 1000))
        self.departure_ms = max(1_000, int(float(departure_seconds) * 1000))
        self.min_hold_ms = max(0, int(float(min_hold_seconds) * 1000))
        self.flies = {
            f"fly-{index:03d}": _ServerFly(f"fly-{index:03d}")
            for index in range(1, self.expected_agents + 1)
        }

    def reset_fly(self, fly_id: str) -> None:
        fly = self.flies.get(str(fly_id))
        if fly is None:
            return
        fly.target_habitat_id = None
        fly.phase = "approach"
        fly.phase_started_ms = 0
        fly.buy_sent = False
        fly.cycle += 1

    def needs_recovery(self, fly_id: str) -> bool:
        """Whether a released runtime slot still has an old visit cached."""

        fly = self.flies.get(str(fly_id))
        return bool(fly and fly.buy_sent)

    def step(
        self,
        timestamp_ms: int,
        habitats: Sequence[Mapping[str, Any]],
        positions: Mapping[str, Mapping[str, Any]],
    ) -> tuple[FlyObservation, ...]:
        """Advance every server fly and return observer-compatible telemetry."""

        valid = [item for item in habitats if isinstance(item.get("id"), str)]
        if not valid:
            return ()
        by_id = {str(item["id"]): item for item in valid}
        observations: list[FlyObservation] = []
        for index, (fly_id, fly) in enumerate(self.flies.items()):
            position = positions.get(fly_id, {})
            state = str(position.get("state") or "EXPLORING").upper()
            held_token = str(position.get("tokenAddress") or "").lower()
            entry_ms = _int(position.get("entryTimestampMs"), 0)
            held_habitat = next(
                (
                    habitat
                    for habitat in valid
                    if str(habitat.get("tokenAddress") or "").lower() == held_token
                    and held_token
                ),
                None,
            )

            if state in {"HOLDING", "DEPARTING"} and held_habitat is not None:
                target_id = str(held_habitat["id"])
                if fly.target_habitat_id != target_id:
                    fly.target_habitat_id = target_id
                    fly.phase = "dwell" if state == "HOLDING" else "depart"
                    fly.phase_started_ms = min(timestamp_ms, entry_ms or timestamp_ms)
                    fly.buy_sent = True
                if state == "DEPARTING" or (entry_ms and timestamp_ms >= entry_ms + self.min_hold_ms):
                    fly.phase = "depart"
            elif state == "EXPLORING" and fly.buy_sent:
                # A confirmed sell or a deterministic pre-broadcast failure
                # released this slot. Clear the observer's old visit on the
                # server loop before selecting the next habitat.
                if fly.phase == "depart" or timestamp_ms - fly.phase_started_ms >= self.departure_ms:
                    fly.target_habitat_id = None
                    fly.phase = "approach"
                    fly.phase_started_ms = timestamp_ms
                    fly.buy_sent = False
                    fly.cycle += 1

            if fly.target_habitat_id not in by_id:
                fly.target_habitat_id = self._choose_target(index, fly, valid)
                fly.phase = "approach"
                fly.phase_started_ms = timestamp_ms
                fly.buy_sent = False

            target = by_id[fly.target_habitat_id]
            if fly.phase == "approach":
                elapsed = max(0, timestamp_ms - fly.phase_started_ms)
                progress = min(1.0, elapsed / self.approach_ms)
                if progress >= 1.0:
                    fly.phase = "dwell"
                    fly.phase_started_ms = timestamp_ms
                distance = _contact_radius(target) * (1.25 - 0.95 * progress) + 0.04
                contact = False
            elif fly.phase == "depart":
                elapsed = max(0, timestamp_ms - fly.phase_started_ms)
                distance = _contact_radius(target) + 0.08 + min(0.22, elapsed / 1000.0 * 0.01)
                contact = False
            else:
                distance = _contact_radius(target) * 0.35
                contact = True
                if state in {"QUALIFYING", "HOLDING", "DEPARTING"} or timestamp_ms - fly.phase_started_ms >= 3_000:
                    fly.buy_sent = True

            # The observer only uses position for metrics, but keeping a
            # deterministic, finite point makes the server feed inspectable.
            observations.append(
                FlyObservation(
                    fly_id=fly_id,
                    timestamp_ms=timestamp_ms,
                    position=(float(index) * 0.1, 0.0, float(distance)),
                    habitats=tuple(
                        HabitatObservation(
                            habitat_id=str(habitat["id"]),
                            distance_m=distance if habitat is target else distance + 0.5,
                            radius_m=_contact_radius(habitat),
                            contact=contact and habitat is target,
                        )
                        for habitat in valid
                    ),
                )
            )
        return tuple(observations)

    @staticmethod
    def _choose_target(index: int, fly: _ServerFly, habitats: Sequence[Mapping[str, Any]]) -> str:
        slot = (index + fly.cycle) % len(habitats)
        return str(habitats[slot]["id"])


def _contact_radius(habitat: Mapping[str, Any]) -> float:
    try:
        physical = max(0.0, float(habitat.get("physicalRadiusM") or 0.0))
    except (TypeError, ValueError):
        physical = 0.0
    return max(0.045, physical * 0.55 + 0.025)


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
