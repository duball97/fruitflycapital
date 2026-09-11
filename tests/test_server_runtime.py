from malecns.swarm.observer import SwarmObserver
from malecns.swarm.server_runtime import ServerSwarmRuntime


def _habitats():
    return [{
        "id": "habitat-1",
        "tokenAddress": "0x1111111111111111111111111111111111111111",
        "physicalRadiusM": 0.1,
    }]


def test_server_runtime_creates_contact_telemetry_without_browser_state():
    runtime = ServerSwarmRuntime(1, approach_seconds=1, departure_seconds=1, min_hold_seconds=5)
    observations = runtime.step(0, _habitats(), {"fly-001": {"state": "EXPLORING"}})
    assert observations[0].fly_id == "fly-001"
    assert observations[0].habitats[0].contact is False

    runtime.step(1_000, _habitats(), {"fly-001": {"state": "EXPLORING"}})
    observations = runtime.step(2_000, _habitats(), {"fly-001": {"state": "EXPLORING"}})
    assert observations[0].habitats[0].contact is True


def test_server_runtime_starts_restored_holding_inside_then_departures():
    runtime = ServerSwarmRuntime(1, approach_seconds=1, departure_seconds=1, min_hold_seconds=5)
    position = {
        "state": "HOLDING",
        "tokenAddress": "0x1111111111111111111111111111111111111111",
        "entryTimestampMs": 0,
    }
    observer = SwarmObserver(1, sustained_dwell_s=1, departure_debounce_s=1, min_hold_s=5)
    observer.sync_active_commitments({"fly-001": ("habitat-1", 0)})

    for timestamp in range(0, 4_000, 1_000):
        observer.ingest(runtime.step(timestamp, _habitats(), {"fly-001": position}))
    assert not [intent for intent in observer.snapshot().behavior_intents if intent.side == "buy"]

    position["state"] = "DEPARTING"
    intents = []
    for timestamp in range(5_000, 8_000, 1_000):
        snapshot = observer.ingest(runtime.step(timestamp, _habitats(), {"fly-001": position}))
        intents.extend(snapshot.behavior_intents)
    assert any(intent.side == "sell" for intent in intents)
