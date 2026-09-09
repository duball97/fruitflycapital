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
from typing import Any

from .brain.realtime import LiveMaleCNSRuntime, RealtimeRuntimeUnavailable, default_realtime_cache
from .brain.sensory_encoding import default_encoder
from .motor.flight_decoder import FlightMotorDecoder
from .market.signal_engine import MarketSignalEngine


SENSORY_ENCODER = default_encoder()
_ANNOTATIONS = Path(__file__).resolve().parents[2] / "data" / "raw" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
FLIGHT_DECODER = FlightMotorDecoder.from_malecns_annotations(_ANNOTATIONS) if _ANNOTATIONS.exists() else FlightMotorDecoder({})
MARKET_ENGINE = MarketSignalEngine.from_env()
REALTIME_CACHE = Path(os.getenv("MALECNS_REALTIME_CACHE", str(default_realtime_cache())))
REALTIME_SEED = int(os.getenv("MALECNS_REALTIME_SEED", "0"))
REALTIME_WINDOW_MS = float(os.getenv("MALECNS_REALTIME_WINDOW_MS", "50"))


def _stable_fly_seed(fly_id: str) -> int:
    """Give each fly a deterministic but independent RNG stream."""
    offset = sum((index + 1) * ord(character) for index, character in enumerate(fly_id))
    return REALTIME_SEED + offset


def command_for_sensor_frame(
    message: Mapping[str, Any],
    runtime: LiveMaleCNSRuntime | None = None,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    """Run one sensory frame through the live runtime when available."""

    stimulation = SENSORY_ENCODER.encode(message.get("sensors", {}))
    if runtime is not None:
        step = runtime.step(stimulation)
        return step.decoded.command.as_actuators(), step.decoded.as_dict(), {
            "stimulation": stimulation,
            "spikeRates": {str(body_id): rate for body_id, rate in step.spike_rates.items()},
            "source": "brian2-malecns-v1-realtime-3hop",
        }
    rates = message.get("spikeRates", {})
    counts = message.get("spikeCounts", {})
    decoded = FLIGHT_DECODER.decode(rates if isinstance(rates, Mapping) else {}, counts if isinstance(counts, Mapping) else None)
    return decoded.command.as_actuators(), decoded.as_dict(), {"stimulation": stimulation, "source": "decoder-without-live-provider"}


async def handle_client(websocket: Any) -> None:
    await websocket.send(json.dumps({"type": "hello", "protocol": "male-cns-fly-world", "version": 1}))
    runtimes: dict[str, LiveMaleCNSRuntime | None] = {}
    async for raw in websocket:
        try:
            message = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(message, dict) or message.get("type") != "brain_input":
            if isinstance(message, dict) and message.get("type") == "environment_request":
                if MARKET_ENGINE is None:
                    environment = {"source": "graph-uniswap", "status": "disabled", "observedAtMs": 0, "habitats": [], "rawMarketFieldsForwardedToFly": False}
                else:
                    environment = await asyncio.to_thread(MARKET_ENGINE.snapshot_if_due)
                await websocket.send(json.dumps({"type": "environment_update", "environment": environment}))
            continue
        fly_id = message.get("flyId")
        if not isinstance(fly_id, str):
            continue
        if fly_id not in runtimes:
            try:
                runtimes[fly_id] = LiveMaleCNSRuntime(
                    REALTIME_CACHE,
                    seed=_stable_fly_seed(fly_id),
                    window_ms=REALTIME_WINDOW_MS,
                )
                print(f"Live Brian2 MaleCNS runtime ready for {fly_id} from {REALTIME_CACHE}", flush=True)
            except (RealtimeRuntimeUnavailable, FileNotFoundError, ImportError, ValueError) as error:
                runtimes[fly_id] = None
                print(f"Live Brian2 runtime unavailable for {fly_id}: {error}", flush=True)
        commands, decoded, runtime_metadata = command_for_sensor_frame(message, runtimes[fly_id])
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
        await websocket.send(json.dumps(output))


async def serve_forever(host: str, port: int) -> None:
    from websockets.asyncio.server import serve

    async with serve(handle_client, host, port, max_size=1_000_000):
        print(f"MaleCNS WebSocket adapter listening on ws://{host}:{port}", flush=True)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(serve_forever(args.host, args.port))


if __name__ == "__main__":
    main()
