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
import logging
import os
import threading
import time
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from websockets.exceptions import ConnectionClosed

from .config import load_project_env
from .brain.realtime import LiveMaleCNSRuntime, RealtimeRuntimeUnavailable, default_realtime_cache
from .brain.sensory_encoding import default_encoder
from .motor.flight_decoder import FlightMotorDecoder
from .market.signal_engine import MarketSignalEngine
from .swarm.observer import FlyObservation, HabitatObservation, SwarmObserver
from .fund.pipeline import SwarmDecisionPipeline
from .fund.service import FundService
from .fund.autonomous import AutonomousTradingRuntime


class _NormalWebSocketCloseFilter(logging.Filter):
    """Keep expected browser disconnects out of the server error stream."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() not in {
            "opening handshake failed",
            "connection handler failed",
            "keepalive ping failed",
        }:
            return True
        if not record.exc_info:
            return True
        return not isinstance(record.exc_info[1], ConnectionClosed)


WEBSOCKET_LOGGER = logging.getLogger("fruitfly.brain.websocket")
WEBSOCKET_LOGGER.addFilter(_NormalWebSocketCloseFilter())


load_project_env()

SENSORY_ENCODER = default_encoder()
_ANNOTATIONS = Path(__file__).resolve().parents[2] / "data" / "raw" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
FLIGHT_DECODER = FlightMotorDecoder.from_malecns_annotations(_ANNOTATIONS) if _ANNOTATIONS.exists() else FlightMotorDecoder({})
MARKET_ENGINE = MarketSignalEngine.from_env()
REALTIME_CACHE = Path(os.getenv("MALECNS_REALTIME_CACHE", str(default_realtime_cache())))
REALTIME_SEED = int(os.getenv("MALECNS_REALTIME_SEED", "0"))
REALTIME_WINDOW_MS = float(os.getenv("MALECNS_REALTIME_WINDOW_MS", "50"))
try:
    _configured_swarm_size = int(os.getenv("NEUROSWARM_SWARM_SIZE", "8"))
except ValueError:
    _configured_swarm_size = 8
SWARM_SIZE = max(1, min(100, _configured_swarm_size))
# Keep the live proposal stream deliberately calm. Environment values may
# increase these windows, but cannot silently make the feed more aggressive.
BEHAVIOR_DWELL_SECONDS = max(3.0, float(os.getenv("FUND_BEHAVIOR_DWELL_SECONDS", "3.0")))
BEHAVIOR_DEPARTURE_DEBOUNCE_SECONDS = max(6.0, float(os.getenv("FUND_BEHAVIOR_DEPARTURE_DEBOUNCE_SECONDS", "6.0")))
BEHAVIOR_INTENT_COOLDOWN_SECONDS = max(90.0, float(os.getenv("FUND_BEHAVIOR_INTENT_COOLDOWN_SECONDS", "90.0")))
SWARM_DECISIONS = SwarmDecisionPipeline(
    max(1, SWARM_SIZE),
    observer=SwarmObserver(
        max(1, SWARM_SIZE),
        sustained_dwell_s=BEHAVIOR_DWELL_SECONDS,
        departure_debounce_s=BEHAVIOR_DEPARTURE_DEBOUNCE_SECONDS,
        min_hold_s=120.0,
        intent_cooldown_s=BEHAVIOR_INTENT_COOLDOWN_SECONDS,
    ),
)
FUND_SERVICE = FundService.from_env()
AUTONOMOUS_RUNTIME = AutonomousTradingRuntime.from_env(FUND_SERVICE.ledger, FUND_SERVICE.wallet)


def _sync_restored_fly_commitments() -> None:
    """Give the behavior observer the durable holdings known by the fund.

    The observer is rebuilt in memory whenever the brain server restarts. The
    ledger is still authoritative for already-held positions, so restore those
    fly-to-habitat links before processing the next telemetry frame.
    """
    commitments: dict[str, tuple[str, int]] = {}
    for fly_id, position in AUTONOMOUS_RUNTIME.positions.items():
        if position.state != "HOLDING" or not position.token_address:
            continue
        for habitat_id, token in AUTONOMOUS_RUNTIME.tokens.items():
            if int(token.chain_id) != int(position.chain_id or token.chain_id):
                continue
            if token.address.lower() != position.token_address.lower():
                continue
            commitments[fly_id] = (habitat_id, int(position.entry_timestamp_ms or 0))
            break
    SWARM_DECISIONS.observer.sync_active_commitments(commitments)


class SwarmProducerLease:
    """Allow exactly one browser connection to author swarm telemetry."""

    def __init__(self, stale_after_s: float | None = None) -> None:
        self._producer: Any | None = None
        # A browser tab can disappear without a WebSocket close frame (mobile
        # sleep, a proxy reset, or a crashed tab). Keep the single-writer
        # invariant, but let a healthy new tab take over after the old writer
        # has stopped sending telemetry.
        if stale_after_s is None:
            try:
                stale_after_s = float(os.getenv("NEUROSWARM_PRODUCER_STALE_SECONDS", "8.0"))
            except ValueError:
                stale_after_s = 8.0
        self.stale_after_s = max(1.0, float(stale_after_s))
        self._last_activity = 0.0
        self._lock: asyncio.Lock | None = None

    async def claim(self, connection: Any, *, prefer: bool = False) -> str:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = time.monotonic()
            stale = self._producer is not None and now - self._last_activity > self.stale_after_s
            if self._producer is None or self._producer is connection or stale or prefer:
                self._producer = connection
                self._last_activity = now
                return "producer"
            return "observer"

    async def release(self, connection: Any) -> bool:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._producer is not connection:
                return False
            self._producer = None
            self._last_activity = 0.0
            return True

    async def touch(self, connection: Any) -> bool:
        """Refresh the active writer lease after accepted telemetry."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._producer is not connection:
                return False
            self._last_activity = time.monotonic()
            return True

    async def is_producer(self, connection: Any) -> bool:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            return self._producer is connection


TELEMETRY_PRODUCER = SwarmProducerLease()
CONNECTED_CLIENTS: set[Any] = set()
LATEST_SWARM_UPDATE: dict[str, Any] | None = None
FUND_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
FUND_RESPONSE_LOCKS: dict[str, asyncio.Lock] = {}
FUND_RESPONSE_TTL_SECONDS = max(1.0, float(os.getenv("FUND_RESPONSE_TTL_SECONDS", "5.0")))
# Brian2 runtime construction must remain on the main interpreter thread, but
# stepping an already-built network can be moved out of the asyncio loop. A
# single lock keeps Brian2's process-wide clock/RNG state from being advanced
# concurrently by different fly runtimes while allowing health, telemetry,
# and portfolio requests to continue being served.
BRAIN_STEP_LOCK = threading.Lock()


async def _broadcast(payload: Mapping[str, Any]) -> None:
    """Send one authoritative server event to every connected screen."""

    raw = json.dumps(dict(payload))
    clients = tuple(CONNECTED_CLIENTS)
    if not clients:
        return
    results = await asyncio.gather(
        *(client.send(raw) for client in clients),
        return_exceptions=True,
    )
    for client, result in zip(clients, results):
        if isinstance(result, BaseException):
            CONNECTED_CLIENTS.discard(client)


async def _fund_response(request_type: str) -> dict[str, Any]:
    """Build fund payloads without ever blocking the WebSocket event loop.

    Wallet snapshots make synchronous JSON-RPC calls. Several screens can ask
    for the same snapshot at once, so cache the short-lived result and
    serialize refreshes per response type. Brian frames, health probes, and
    new WebSocket handshakes remain responsive while the RPC request runs.
    """

    now = time.monotonic()
    cached = FUND_RESPONSE_CACHE.get(request_type)
    if cached is not None and now - cached[0] < FUND_RESPONSE_TTL_SECONDS:
        return cached[1]

    lock = FUND_RESPONSE_LOCKS.setdefault(request_type, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = FUND_RESPONSE_CACHE.get(request_type)
        if cached is not None and now - cached[0] < FUND_RESPONSE_TTL_SECONDS:
            return cached[1]

        if request_type == "fund_status_request":
            fund = await asyncio.to_thread(FUND_SERVICE.status)
            response = {
                "type": "fund_status_update",
                "fund": {**fund, "autonomous": AUTONOMOUS_RUNTIME.snapshot()},
                "demoData": False,
            }
        elif request_type == "portfolio_request":
            portfolio = await asyncio.to_thread(FUND_SERVICE.portfolio_update)
            portfolio["fund"]["autonomous"] = AUTONOMOUS_RUNTIME.snapshot()
            response = {"type": "portfolio_update", **portfolio}
        else:
            history = await asyncio.to_thread(FUND_SERVICE.trade_history)
            response = {"type": "trade_history_update", **history}

        FUND_RESPONSE_CACHE[request_type] = (time.monotonic(), response)
        return response


async def _process_brain_input(message: Mapping[str, Any]) -> None:
    """Complete one brain frame independently of the socket reader.

    The producer sends brain frames more frequently than the market observer
    needs telemetry. Keeping this work in a child task means a slow Brian2
    step cannot hold the connection's receive loop hostage. ``BrainSocket``
    already limits each fly to one in-flight frame, so this remains bounded to
    one task per primary fly.
    """

    fly_id = message.get("flyId")
    if not isinstance(fly_id, str):
        return
    try:
        # Runtime construction stays on the main interpreter thread. The
        # worker-thread boundary is only for stepping an existing runtime.
        runtime = await RUNTIME_REGISTRY.get(fly_id)
        commands, decoded, runtime_metadata = await asyncio.to_thread(
            _step_sensor_frame,
            message,
            runtime,
        )
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
        await _broadcast(output)
    except (ConnectionError, ConnectionClosed):
        return
    except Exception:
        # A single malformed or failed neural frame must not terminate the
        # authoritative telemetry connection. The next frame can recover.
        WEBSOCKET_LOGGER.exception("brain input processing failed for %s", fly_id)


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
        max_live_runtimes: int | None = None,
        runtime_factory: Callable[..., LiveMaleCNSRuntime] = LiveMaleCNSRuntime,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.base_seed = int(base_seed)
        self.window_ms = float(window_ms)
        self.max_live_runtimes = None if max_live_runtimes is None else max(1, int(max_live_runtimes))
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
            live_count = sum(runtime is not None for runtime in self._runtimes.values())
            if self.max_live_runtimes is not None and live_count >= self.max_live_runtimes:
                # One cached Brian2 network costs roughly 120 MB for the
                # current 3-hop MaleCNS graph. Render's 512 MB instances can't
                # safely own sixteen copies. Preserve the independent fly IDs
                # and return decoder output for overflow agents instead of
                # letting the operating system kill the entire WebSocket.
                self._runtimes[fly_id] = None
                print(
                    f"Live Brian2 capacity {self.max_live_runtimes} reached; "
                    f"using decoder fallback for {fly_id}",
                    flush=True,
                )
                return None
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
    max_live_runtimes=int(
        os.getenv(
            "MALECNS_MAX_LIVE_RUNTIMES",
            "2" if os.getenv("RENDER") else str(SWARM_SIZE),
        )
    ),
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


def _step_sensor_frame(
    message: Mapping[str, Any],
    runtime: LiveMaleCNSRuntime | None,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    """Run one brain frame without blocking the WebSocket event loop.

    ``RuntimeRegistry.get`` intentionally stays on the main thread because
    Brian2's network construction installs signal handlers. Once a runtime
    exists, its fixed-window step is protected and executed by the worker
    thread so a burst of brain frames cannot delay swarm telemetry.
    """

    with BRAIN_STEP_LOCK:
        return command_for_sensor_frame(message, runtime)


async def handle_client(websocket: Any) -> None:
    global LATEST_SWARM_UPDATE
    CONNECTED_CLIENTS.add(websocket)
    brain_tasks: set[asyncio.Task[Any]] = set()

    def remember_brain_task(task: asyncio.Task[Any]) -> None:
        brain_tasks.add(task)
        task.add_done_callback(brain_tasks.discard)

    try:
        await websocket.send(json.dumps({"type": "hello", "protocol": "male-cns-fly-world", "version": 1}))
        async for raw in websocket:
            try:
                message = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict) and message.get("type") == "swarm_claim":
                role = await TELEMETRY_PRODUCER.claim(
                    websocket,
                    prefer=bool(message.get("preferredProducer")),
                )
                try:
                    await websocket.send(json.dumps({"type": "swarm_role", "role": role}))
                    if role == "observer" and LATEST_SWARM_UPDATE is not None:
                        await websocket.send(json.dumps(LATEST_SWARM_UPDATE))
                except (ConnectionError, ConnectionClosed):
                    break
                continue
            if isinstance(message, dict) and message.get("type") == "swarm_telemetry":
                # Backward-compatible implicit claim for an older frontend,
                # but never accept telemetry from a second connection.
                if not await TELEMETRY_PRODUCER.is_producer(websocket):
                    role = await TELEMETRY_PRODUCER.claim(websocket)
                    try:
                        await websocket.send(json.dumps({"type": "swarm_role", "role": role}))
                    except (ConnectionError, ConnectionClosed):
                        break
                    if role != "producer":
                        continue
                await TELEMETRY_PRODUCER.touch(websocket)
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
                    LATEST_SWARM_UPDATE = {"type": "swarm_update", "decision": decision_payload}
                    try:
                        await _broadcast(LATEST_SWARM_UPDATE)
                    except (ConnectionError, ConnectionClosed):
                        break
                continue
            if isinstance(message, dict) and message.get("type") in {"fund_status_request", "portfolio_request", "trade_history_request"}:
                request_type = message["type"]
                response = await _fund_response(request_type)
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
                    _sync_restored_fly_commitments()
                    try:
                        await websocket.send(json.dumps({"type": "environment_update", "environment": environment}))
                    except (ConnectionError, ConnectionClosed):
                        break
                continue
            fly_id = message.get("flyId")
            if not isinstance(fly_id, str):
                continue
            # Do not await Brian2 here. The receive loop must remain free to
            # accept the producer's higher-priority swarm telemetry and new
            # viewer handshakes while brain frames are being stepped.
            remember_brain_task(asyncio.create_task(_process_brain_input(message)))
    except (ConnectionError, ConnectionClosed):
        # Browsers and Render's proxy can drop an idle websocket without a
        # close frame. This is a normal client lifecycle event, not a server
        # error that should fill the logs or take down the process.
        return
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        if await TELEMETRY_PRODUCER.release(websocket):
            await _broadcast({"type": "swarm_role", "role": "available"})


def process_http_request(connection: Any, request: Any) -> Any | None:
    """Serve Render health probes without consuming WebSocket upgrades.

    Render routes a Web Service only while its HTTP endpoint is healthy.  A
    bare ``websockets`` server accepts upgrades but doesn't provide a useful
    response to an ordinary GET, which can leave the service listening inside
    the container while the public hostname times out.  Keep ``/`` and
    ``/healthz`` cheap and deterministic; real WebSocket requests continue to
    the normal opening handshake.
    """

    if str(request.headers.get("Upgrade", "")).lower() == "websocket":
        return None
    path = str(request.path).split("?", 1)[0]
    if path in {"/", "/healthz"}:
        response = connection.respond(
            HTTPStatus.OK,
            json.dumps({"status": "ok", "service": "fruitfly-brain"}) + "\n",
        )
        del response.headers["Content-Type"]
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        return response
    return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")


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

    # Build the bounded live population before accepting browser connections.
    # Brian2 construction is intentionally kept on the main interpreter
    # thread, and doing it after ``serve`` starts makes the socket look alive
    # while the first page request is blocked for several seconds per fly.
    # Prewarming makes startup honest and prevents the first producer from
    # timing out while the runtimes are being created.
    prewarm_count = RUNTIME_REGISTRY.max_live_runtimes or 0
    if prewarm_count > 0:
        print(f"Prewarming MaleCNS runtimes ({prewarm_count})...", flush=True)
        for index in range(prewarm_count):
            await RUNTIME_REGISTRY.get(f"fly-{index + 1:03d}")

    async with serve(
        handle_client,
        host,
        port,
        max_size=1_000_000,
        process_request=process_http_request,
        ping_interval=20,
        # Background tabs and short network stalls should not make the shared
        # brain runtime look dead. Closed clients are still removed by the
        # handler cleanup path and by failed broadcasts.
        ping_timeout=None,
        close_timeout=5,
        logger=WEBSOCKET_LOGGER,
    ):
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
