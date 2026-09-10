"""WebSocket adapter for the browser fly world.

The adapter keeps transport, sensory encoding, Brian2 activity, and motor
decoding separate. When the explicit official-data realtime cache exists, it
advances one persistent MaleCNS runtime per connected fly and returns the
resulting rates. Without that cache, it correctly returns zero flight drive
and reports the missing provider instead of fabricating spikes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from websockets.exceptions import ConnectionClosed

from .config import load_project_env
from .brain.realtime import LiveMaleCNSRuntime, RealtimeRuntimeUnavailable, default_realtime_cache
from .brain.sensory_encoding import default_encoder
from .motor.flight_decoder import FlightMotorDecoder
from .market.signal_engine import MarketSignalEngine
from .swarm.observer import FlyObservation, HabitatObservation
from .fund.pipeline import SwarmDecisionPipeline
from .fund.service import FundService
from .fund.autonomous import AutonomousTradingRuntime


load_project_env()

SENSORY_ENCODER = default_encoder()
_ANNOTATIONS = Path(__file__).resolve().parents[2] / "data" / "raw" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
FLIGHT_DECODER = FlightMotorDecoder.from_malecns_annotations(_ANNOTATIONS) if _ANNOTATIONS.exists() else FlightMotorDecoder({})
MARKET_ENGINE = MarketSignalEngine.from_env()
REALTIME_CACHE = Path(os.getenv("MALECNS_REALTIME_CACHE", str(default_realtime_cache())))
REALTIME_SEED = int(os.getenv("MALECNS_REALTIME_SEED", "0"))
REALTIME_WINDOW_MS = float(os.getenv("MALECNS_REALTIME_WINDOW_MS", "50"))
SWARM_SIZE = 16
SWARM_DECISIONS = SwarmDecisionPipeline(max(1, SWARM_SIZE))
FUND_SERVICE = FundService.from_env()
AUTONOMOUS_RUNTIME = AutonomousTradingRuntime.from_env(FUND_SERVICE.ledger, FUND_SERVICE.wallet)


def _stable_fly_seed(fly_id: str, base_seed: int = REALTIME_SEED) -> int:
    """Give each fly a deterministic but independent RNG stream."""
    offset = sum((index + 1) * ord(character) for index, character in enumerate(fly_id))
    return int(base_seed) + offset


class RuntimeRegistry:
    """Own one persistent neural runtime per distinct fly ID.

    This is the server-side population boundary. A browser reconnect reuses
    the same runtime objects, while two IDs always receive separate Brian2
    state and separate deterministic seeds. ``runtime_factory`` is injectable
    so the ownership contract can be tested without loading the large cache.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        base_seed: int = 0,
        window_ms: float = 50.0,
        runtime_factory: Callable[..., LiveMaleCNSRuntime] = LiveMaleCNSRuntime,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.base_seed = int(base_seed)
        self.window_ms = float(window_ms)
        self.runtime_factory = runtime_factory
        self._runtimes: dict[str, LiveMaleCNSRuntime | None] = {}
        self._lock: asyncio.Lock | None = None

    @property
    def runtime_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._runtimes))

    async def get(self, fly_id: str) -> LiveMaleCNSRuntime | None:
        if fly_id in self._runtimes:
            return self._runtimes[fly_id]
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if fly_id in self._runtimes:
                return self._runtimes[fly_id]
            try:
                # Brian2's runtime and code-generation stack must be created
                # on Python's main interpreter thread. Moving construction to
                # asyncio's worker pool triggers its signal-handler guard on
                # Render ("signal only works in main thread"). The websocket
                # loop is already the process' main thread, so keep the
                # ownership boundary here and yield only between requests.
                runtime = self.runtime_factory(
                    self.cache_dir,
                    seed=_stable_fly_seed(fly_id, self.base_seed),
                    window_ms=self.window_ms,
                )
                self._runtimes[fly_id] = runtime
                print(f"Live Brian2 MaleCNS runtime ready for {fly_id} from {self.cache_dir}", flush=True)
            except (RealtimeRuntimeUnavailable, FileNotFoundError, ImportError, ValueError) as error:
                self._runtimes[fly_id] = None
                print(f"Live Brian2 runtime unavailable for {fly_id}: {error}", flush=True)
            return self._runtimes[fly_id]


RUNTIME_REGISTRY = RuntimeRegistry(
    REALTIME_CACHE,
    base_seed=REALTIME_SEED,
    window_ms=REALTIME_WINDOW_MS,
)


def command_for_sensor_frame(
    message: Mapping[str, Any],
    runtime: LiveMaleCNSRuntime | None = None,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    """Run one sensory frame through the live runtime when available."""

    stimulation = SENSORY_ENCODER.encode(message.get("sensors", {}))
    if runtime is not None:
        step = runtime.step(stimulation)
        return step.decoded.as_actuators(), step.decoded.as_dict(), {
            "stimulation": stimulation,
            "spikeRates": {str(body_id): rate for body_id, rate in step.spike_rates.items()},
            "source": f"brian2-malecns-v1-realtime-{runtime.manifest.get('path_hops', 3)}hop",
        }
    rates = message.get("spikeRates", {})
    counts = message.get("spikeCounts", {})
    decoded = FLIGHT_DECODER.decode(rates if isinstance(rates, Mapping) else {}, counts if isinstance(counts, Mapping) else None)
    return decoded.as_actuators(), decoded.as_dict(), {"stimulation": stimulation, "source": "decoder-without-live-provider"}


async def handle_client(websocket: Any) -> None:
    try:
        await websocket.send(json.dumps({"type": "hello", "protocol": "male-cns-fly-world", "version": 1}))
        async for raw in websocket:
            try:
                message = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict) and message.get("type") == "swarm_telemetry":
                observations = _parse_swarm_telemetry(message)
                if observations:
                    decision = await asyncio.to_thread(SWARM_DECISIONS.ingest, observations)
                    autonomous = await asyncio.to_thread(
                        AUTONOMOUS_RUNTIME.ingest,
                        decision.behavior_intents,
                        observed_at_ms=decision.observed_at_ms,
                    )
                    decision_payload = decision.as_dict()
                    decision_payload["autonomousTrading"] = autonomous
                    try:
                        await websocket.send(json.dumps({"type": "swarm_update", "decision": decision_payload}))
                    except (ConnectionError, ConnectionClosed):
                        break
                continue
            if isinstance(message, dict) and message.get("type") in {"fund_status_request", "portfolio_request", "trade_history_request"}:
                request_type = message["type"]
                if request_type == "fund_status_request":
                        response = {"type": "fund_status_update", "fund": {**FUND_SERVICE.status(), "autonomous": AUTONOMOUS_RUNTIME.snapshot()}, "demoData": False}
                elif request_type == "portfolio_request":
                    portfolio = FUND_SERVICE.portfolio_update()
                    portfolio["fund"]["autonomous"] = AUTONOMOUS_RUNTIME.snapshot()
                    response = {"type": "portfolio_update", **portfolio}
                else:
                    response = {"type": "trade_history_update", **FUND_SERVICE.trade_history()}
                try:
                    await websocket.send(json.dumps(response))
                except (ConnectionError, ConnectionClosed):
                    break
                continue
            if not isinstance(message, dict) or message.get("type") != "brain_input":
                if isinstance(message, dict) and message.get("type") == "environment_request":
                    if MARKET_ENGINE is None:
                        environment = {
                            "source": "graph-uniswap",
                            "status": "disabled",
                            "observedAtMs": 0,
                            "habitats": [],
                            "rawMarketFieldsForwardedToFly": False,
                            "reason": "configure Graph credentials plus NEUROSWARM_MARKET_HABITATS, or enable DexScreener discovery",
                        }
                    else:
                        environment = await asyncio.to_thread(MARKET_ENGINE.snapshot_if_due)
                    AUTONOMOUS_RUNTIME.update_habitats(environment.get("habitats", []))
                    try:
                        await websocket.send(json.dumps({"type": "environment_update", "environment": environment}))
                    except (ConnectionError, ConnectionClosed):
                        break
                continue
            fly_id = message.get("flyId")
            if not isinstance(fly_id, str):
                continue
            runtime = await RUNTIME_REGISTRY.get(fly_id)
            # Keep all Brian2 construction and stepping on the same main
            # interpreter thread. The previous to_thread call caused every
            # Render runtime to fail before it could produce a neural command.
            commands, decoded, runtime_metadata = command_for_sensor_frame(message, runtime)
            output = {
                "type": "brain_output",
                "flyId": fly_id,
                "commands": commands,
                "timestampMs": int(asyncio.get_running_loop().time() * 1000),
                "source": runtime_metadata["source"],
                "stimulation": runtime_metadata["stimulation"],
                **decoded,
            }
            if "spikeRates" in runtime_metadata:
                output["spikeRates"] = runtime_metadata["spikeRates"]
            try:
                await websocket.send(json.dumps(output))
            except (ConnectionError, ConnectionClosed):
                break
    except (ConnectionError, ConnectionClosed):
        # Browsers and Render's proxy can drop an idle websocket without a
        # close frame. This is a normal client lifecycle event, not a server
        # error that should fill the logs or take down the process.
        return


def _parse_swarm_telemetry(message: Mapping[str, Any]) -> tuple[FlyObservation, ...]:
    """Parse browser telemetry without forwarding it to any CNS runtime."""

    raw_agents = message.get("agents")
    if not isinstance(raw_agents, list):
        return ()
    observations: list[FlyObservation] = []
    timestamp_ms = _int_value(message.get("timestampMs"), 0)
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, Mapping) or not isinstance(raw_agent.get("flyId"), str):
            continue
        position = _wire_position(raw_agent.get("position"))
        raw_habitats = raw_agent.get("habitats")
        if position is None or not isinstance(raw_habitats, list):
            continue
        habitats: list[HabitatObservation] = []
        for raw_habitat in raw_habitats:
            if not isinstance(raw_habitat, Mapping) or not isinstance(raw_habitat.get("habitatId"), str):
                continue
            habitats.append(
                HabitatObservation(
                    habitat_id=raw_habitat["habitatId"],
                    distance_m=max(0.0, _float_value(raw_habitat.get("distanceM"), 0.0)),
                    radius_m=max(0.0, _float_value(raw_habitat.get("radiusM"), 0.0)),
                    contact=bool(raw_habitat.get("contact", False)),
                )
            )
        if habitats:
            observations.append(
                FlyObservation(
                    fly_id=raw_agent["flyId"],
                    timestamp_ms=_int_value(raw_agent.get("timestampMs"), timestamp_ms),
                    position=position,
                    habitats=tuple(habitats),
                )
            )
    return tuple(observations)


def _wire_position(value: Any) -> tuple[float, float, float] | None:
    if isinstance(value, Mapping):
        return (
            _float_value(value.get("x"), 0.0),
            _float_value(value.get("y"), 0.0),
            _float_value(value.get("z"), 0.0),
        )
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(_float_value(item, 0.0) for item in value)  # type: ignore[return-value]
    return None


def _float_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


async def serve_forever(host: str, port: int) -> None:
    from websockets.asyncio.server import serve

    async with serve(handle_client, host, port, max_size=1_000_000):
        print(f"MaleCNS WebSocket adapter listening on ws://{host}:{port}", flush=True)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # Render supplies PORT and requires a public bind address. Local callers
    # can still override both explicitly, as the README examples do.
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")))
    args = parser.parse_args()
    asyncio.run(serve_forever(args.host, args.port))


if __name__ == "__main__":
    main()
