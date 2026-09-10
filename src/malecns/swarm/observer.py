"""Measure what the independent CNS agents actually do in the world.

This module deliberately observes behavior rather than assigning a preference
to a habitat. It only consumes body telemetry and distances already computed
by the embodied world. Render-only follower bodies must not be sent here.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import sqrt
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class HabitatObservation:
    habitat_id: str
    distance_m: float
    radius_m: float
    contact: bool = False


@dataclass(frozen=True)
class FlyObservation:
    fly_id: str
    timestamp_ms: int
    position: tuple[float, float, float]
    habitats: tuple[HabitatObservation, ...]


@dataclass(frozen=True)
class DistancePoint:
    timestamp_ms: int
    distance_m: float

    def as_dict(self) -> dict[str, Any]:
        return {"timestampMs": self.timestamp_ms, "distanceM": self.distance_m}


@dataclass(frozen=True)
class AgentHabitatBehavior:
    fly_id: str
    habitat_id: str
    visits: int
    approaches: int
    departures: int
    dwell_time_s: float
    repeat_visits: int
    distance_over_time: tuple[DistancePoint, ...]
    contact_time_s: float
    local_congregation: float
    persistence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "flyId": self.fly_id,
            "habitatId": self.habitat_id,
            "visits": self.visits,
            "approaches": self.approaches,
            "departures": self.departures,
            "dwellTimeS": round(self.dwell_time_s, 6),
            "repeatVisits": self.repeat_visits,
            "distanceOverTime": [point.as_dict() for point in self.distance_over_time],
            "contactTimeS": round(self.contact_time_s, 6),
            "localCongregation": round(self.local_congregation, 6),
            "persistence": round(self.persistence, 6),
        }


@dataclass(frozen=True)
class HabitatSwarmSummary:
    habitat_id: str
    expected_agents: int
    observed_agents: int
    visitor_count: int
    visits: int
    approaches: int
    departures: int
    sustained_dwell_count: int
    median_dwell_s: float
    repeat_visit_rate: float
    departure_rate: float
    local_congregation: float
    persistence: float
    contact_time_s: float
    observation_span_s: float
    agent_behaviors: tuple[AgentHabitatBehavior, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "habitatId": self.habitat_id,
            "expectedAgents": self.expected_agents,
            "observedAgents": self.observed_agents,
            "visitorCount": self.visitor_count,
            "visits": self.visits,
            "approaches": self.approaches,
            "departures": self.departures,
            "sustainedDwellCount": self.sustained_dwell_count,
            "medianDwellS": round(self.median_dwell_s, 6),
            "repeatVisitRate": round(self.repeat_visit_rate, 6),
            "departureRate": round(self.departure_rate, 6),
            "localCongregation": round(self.local_congregation, 6),
            "persistence": round(self.persistence, 6),
            "contactTimeS": round(self.contact_time_s, 6),
            "observationSpanS": round(self.observation_span_s, 6),
            "agentBehaviors": [behavior.as_dict() for behavior in self.agent_behaviors],
        }


@dataclass(frozen=True)
class SwarmSnapshot:
    observed_at_ms: int
    habitats: tuple[HabitatSwarmSummary, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observedAtMs": self.observed_at_ms,
            "habitats": [habitat.as_dict() for habitat in self.habitats],
        }


@dataclass
class _Track:
    fly_id: str
    habitat_id: str
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    last_distance_m: float | None = None
    inside: bool = False
    approach_active: bool = False
    visits: int = 0
    approaches: int = 0
    departures: int = 0
    dwell_time_s: float = 0.0
    contact_time_s: float = 0.0
    current_visit_dwell_s: float = 0.0
    visit_dwell_s: list[float] = field(default_factory=list)
    distance_history: deque[DistancePoint] = field(default_factory=deque)
    congregation_sum: float = 0.0
    congregation_samples: int = 0


class SwarmObserver:
    """Accumulate behavior metrics for primary CNS agents.

    ``dwell_time_s`` is integrated only across consecutive samples whose gap
    is no larger than ``max_sample_gap_s``. A reconnect or browser stall cannot
    manufacture a long visit. Approaches count episodes of decreasing distance
    while outside a habitat, rather than counting every telemetry frame.
    """

    def __init__(
        self,
        expected_agents: int,
        *,
        sustained_dwell_s: float = 5.0,
        congregation_radius_m: float = 0.12,
        max_sample_gap_s: float = 2.0,
        distance_history_size: int = 600,
        approach_epsilon_m: float = 0.0005,
    ) -> None:
        if expected_agents < 1:
            raise ValueError("expected_agents must be positive")
        self.expected_agents = expected_agents
        self.sustained_dwell_s = max(0.0, float(sustained_dwell_s))
        self.congregation_radius_m = max(0.001, float(congregation_radius_m))
        self.max_sample_gap_s = max(0.0, float(max_sample_gap_s))
        self.distance_history_size = max(2, int(distance_history_size))
        self.approach_epsilon_m = max(0.0, float(approach_epsilon_m))
        self._tracks: dict[tuple[str, str], _Track] = {}
        self._agent_first_seen: dict[str, int] = {}
        self._agent_last_seen: dict[str, int] = {}
        self._latest_positions: dict[str, tuple[float, float, float]] = {}
        self._latest_timestamp_ms = 0

    def ingest(self, observations: Iterable[FlyObservation]) -> SwarmSnapshot:
        frame = tuple(observations)
        if not frame:
            return self.snapshot()
        timestamp_ms = max(observation.timestamp_ms for observation in frame)
        self._latest_timestamp_ms = max(self._latest_timestamp_ms, timestamp_ms)
        self._latest_positions = {observation.fly_id: observation.position for observation in frame}
        for observation in frame:
            self._agent_first_seen.setdefault(observation.fly_id, observation.timestamp_ms)
            self._agent_last_seen[observation.fly_id] = observation.timestamp_ms

        for observation in frame:
            for habitat in observation.habitats:
                key = (observation.fly_id, habitat.habitat_id)
                track = self._tracks.setdefault(
                    key,
                    _Track(
                        fly_id=observation.fly_id,
                        habitat_id=habitat.habitat_id,
                        distance_history=deque(maxlen=self.distance_history_size),
                    ),
                )
                self._update_track(track, observation, habitat, frame)
        return self.snapshot()

    def snapshot(self) -> SwarmSnapshot:
        habitat_ids = sorted({habitat_id for _, habitat_id in self._tracks})
        summaries = tuple(self._summary(habitat_id) for habitat_id in habitat_ids)
        return SwarmSnapshot(self._latest_timestamp_ms, summaries)

    def _update_track(
        self,
        track: _Track,
        observation: FlyObservation,
        habitat: HabitatObservation,
        frame: tuple[FlyObservation, ...],
    ) -> None:
        timestamp_ms = observation.timestamp_ms
        distance_m = max(0.0, float(habitat.distance_m))
        inside = distance_m <= max(0.0, float(habitat.radius_m))
        previous_inside = track.inside
        dt_s = 0.0
        if track.last_timestamp_ms is not None:
            dt_s = max(0.0, (timestamp_ms - track.last_timestamp_ms) / 1000.0)
            if dt_s > self.max_sample_gap_s:
                dt_s = 0.0

        if track.first_timestamp_ms is None:
            track.first_timestamp_ms = timestamp_ms
        if inside and not previous_inside:
            track.visits += 1
            track.current_visit_dwell_s = 0.0
        if previous_inside and not inside:
            track.departures += 1
            track.visit_dwell_s.append(track.current_visit_dwell_s)
            track.current_visit_dwell_s = 0.0

        if inside:
            track.dwell_time_s += dt_s
            track.current_visit_dwell_s += dt_s
            if habitat.contact:
                track.contact_time_s += dt_s

        decreasing = (
            not inside
            and track.last_distance_m is not None
            and distance_m < track.last_distance_m - self.approach_epsilon_m
        )
        if decreasing and not track.approach_active:
            track.approaches += 1
        track.approach_active = decreasing

        if inside:
            neighbors = 0
            for other in frame:
                if other.fly_id == observation.fly_id:
                    continue
                other_habitat = next((item for item in other.habitats if item.habitat_id == habitat.habitat_id), None)
                if other_habitat is not None and other_habitat.distance_m <= self.congregation_radius_m:
                    neighbors += 1
            track.congregation_sum += neighbors
            track.congregation_samples += 1

        track.distance_history.append(DistancePoint(timestamp_ms, distance_m))
        track.last_timestamp_ms = timestamp_ms
        track.last_distance_m = distance_m
        track.inside = inside

    def _summary(self, habitat_id: str) -> HabitatSwarmSummary:
        tracks = tuple(track for (fly_id, candidate_id), track in self._tracks.items() if candidate_id == habitat_id)
        behaviors = tuple(self._behavior(track) for track in sorted(tracks, key=lambda item: item.fly_id))
        visitors = tuple(behavior for behavior in behaviors if behavior.visits > 0)
        dwell_values = [behavior.dwell_time_s for behavior in visitors]
        visits = sum(behavior.visits for behavior in behaviors)
        repeat_visitors = sum(1 for behavior in visitors if behavior.repeat_visits > 0)
        departures = sum(behavior.departures for behavior in behaviors)
        congregation_values = [behavior.local_congregation for behavior in visitors]
        persistence_values = [behavior.persistence for behavior in visitors]
        timestamps = [timestamp for track in tracks for timestamp in (track.first_timestamp_ms, track.last_timestamp_ms) if timestamp is not None]
        span_s = (max(timestamps) - min(timestamps)) / 1000.0 if timestamps else 0.0
        return HabitatSwarmSummary(
            habitat_id=habitat_id,
            expected_agents=self.expected_agents,
            observed_agents=len({behavior.fly_id for behavior in behaviors}),
            visitor_count=len(visitors),
            visits=visits,
            approaches=sum(behavior.approaches for behavior in behaviors),
            departures=departures,
            sustained_dwell_count=sum(1 for value in dwell_values if value >= self.sustained_dwell_s),
            median_dwell_s=float(median(dwell_values)) if dwell_values else 0.0,
            repeat_visit_rate=repeat_visitors / len(visitors) if visitors else 0.0,
            departure_rate=departures / visits if visits else 0.0,
            local_congregation=sum(congregation_values) / len(congregation_values) if congregation_values else 0.0,
            persistence=sum(persistence_values) / len(persistence_values) if persistence_values else 0.0,
            contact_time_s=sum(behavior.contact_time_s for behavior in behaviors),
            observation_span_s=span_s,
            agent_behaviors=behaviors,
        )

    @staticmethod
    def _behavior(track: _Track) -> AgentHabitatBehavior:
        active_span_s = 0.0
        if track.first_timestamp_ms is not None and track.last_timestamp_ms is not None:
            active_span_s = max(0.0, (track.last_timestamp_ms - track.first_timestamp_ms) / 1000.0)
        denominator = max(active_span_s, track.dwell_time_s, 1e-9)
        return AgentHabitatBehavior(
            fly_id=track.fly_id,
            habitat_id=track.habitat_id,
            visits=track.visits,
            approaches=track.approaches,
            departures=track.departures,
            dwell_time_s=track.dwell_time_s,
            repeat_visits=max(0, track.visits - 1),
            distance_over_time=tuple(track.distance_history),
            contact_time_s=track.contact_time_s,
            local_congregation=(track.congregation_sum / track.congregation_samples if track.congregation_samples else 0.0),
            persistence=min(1.0, track.dwell_time_s / denominator),
        )


def distance_between(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """Small helper for adapters that receive positions and habitat positions."""

    return sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))
