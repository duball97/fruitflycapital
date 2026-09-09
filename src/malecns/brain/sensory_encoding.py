"""Conservative sensory-to-MaleCNS population encoding.

This module consumes sensory observables only. It never accepts or emits a
target/source coordinate. Body IDs come from the checked-in mapping generated
from the official MaleCNS annotation table.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class StimulationEntry:
    body_id: int
    rate_hz: float
    population: str

    def as_dict(self) -> dict[str, Any]:
        return {"bodyId": self.body_id, "rateHz": round(self.rate_hz, 6), "population": self.population}


class MaleCNSSensoryEncoder:
    """Map perceptual summaries to documented MaleCNS input populations.

    ``max_rate_hz`` is an explicit OUR_ASSUMPTION rate encoder. The structural
    IDs and side assignments are MALECNS_DATA; no CNS edges are added here.
    """

    def __init__(self, rows: Iterable[dict[str, str]], *, max_rate_hz: float = 150.0) -> None:
        self.max_rate_hz = max_rate_hz
        self.visual_left = self._ids(rows, "visual_R8d", "L")
        self.visual_right = self._ids(rows, "visual_R8d", "R")
        self.olfactory = self._ids(rows, "olfactory_ORN_DA1", None)
        self.mechanosensory = self._ids(rows, "mechanosensory_auditory_JO-B1_b", None)

    @classmethod
    def from_csv(cls, path: str | Path) -> "MaleCNSSensoryEncoder":
        with Path(path).open(newline="", encoding="utf-8") as handle:
            return cls(list(csv.DictReader(handle)))

    def encode(self, sensors: dict[str, Any]) -> dict[str, Any]:
        left_eye = _mapping(sensors.get("leftEye"))
        right_eye = _mapping(sensors.get("rightEye"))
        odor = _mapping(sensors.get("odor"))
        visual = self._entries(self.visual_left, _bounded_rate(_number(left_eye.get("meanLuminance")), self.max_rate_hz), "R8d")
        visual += self._entries(self.visual_right, _bounded_rate(_number(right_eye.get("meanLuminance")), self.max_rate_hz), "R8d")
        olfactory_rate = _bounded_rate(_number(odor.get("concentration")), self.max_rate_hz)
        olfactory = self._entries(self.olfactory, olfactory_rate, "ORN_DA1")
        return {
            "visual": [entry.as_dict() for entry in visual],
            "olfactory": [entry.as_dict() for entry in olfactory],
            "mechanosensory": [],
            "unimplemented": [
                "aversive_odor_to_maleCNS",
                "optic_flow_to_maleCNS_visual_population",
                "wind_to_maleCNS_mechanosensory",
                "gravity_to_maleCNS_mechanosensory",
                "contact_to_maleCNS_mechanosensory",
            ],
        }

    def _ids(self, rows: Iterable[dict[str, str]], population: str, side: str | None) -> list[int]:
        selected = []
        for row in rows:
            if row.get("population") != population:
                continue
            if side is not None and row.get("side_for_registry") != side:
                continue
            selected.append(int(row["bodyId"]))
        return sorted(selected)

    def _entries(self, body_ids: Iterable[int], rate_hz: float, population: str) -> list[StimulationEntry]:
        return [StimulationEntry(body_id, rate_hz, population) for body_id in body_ids]


def default_encoder() -> MaleCNSSensoryEncoder:
    mapping = Path(__file__).resolve().parents[3] / "data" / "mappings" / "malecns_sensory_motor_ids.csv"
    return MaleCNSSensoryEncoder.from_csv(mapping)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _bounded_rate(value: float, max_rate_hz: float = 150.0) -> float:
    return min(max_rate_hz, max(0.0, value * max_rate_hz))
