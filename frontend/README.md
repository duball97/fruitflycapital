# Fruit Fly Capital / NeuroSwarm frontend

This is a small Three.js/Vite client for the Fruit Fly Capital embodied market
ecology prototype. The product surface is NeuroSwarm; the technical stack is
MaleCNS v1.0, Flybody, Three.js, and The Graph.
Physical positions are in metres and the world is 2 m x 1 m x 2 m. The visible
fly body is loaded from the canonical TuragaLab/Flybody XML and referenced OBJ
meshes; see `../docs/FLYBODY_INTEGRATION.md` for provenance and scale
conversion. The body integrator advances at 120 Hz; rendering is decoupled
with `requestAnimationFrame`.

## Run

From this directory:

```bash
npm install
npm run dev
```

On macOS, use an explicit Python 3.12 environment from the repository root.
Do not use the global `python` command, and do not use the system `python3` if
it is older than 3.10:

```bash
brew install python@3.12
PYTHON312="$(brew --prefix python@3.12)/bin/python3.12"
"$PYTHON312" -m venv .venv312
./.venv312/bin/python -m pip install -e '.[dev,physics,speed]'
./.venv312/bin/python -m malecns.brain_server --host 127.0.0.1 --port 8765
```

The Vite script uses `--force` so stale optimized-dependency responses do not
leave the browser showing `504 Outdated Optimize Dep`. Restart the dev server
after changing dependencies.

In another terminal, the optional Python protocol adapter can be started from
the repository root:

```bash
./.venv312/bin/python -m malecns.brain_server --host 127.0.0.1 --port 8765
```

Before starting the adapter, build the realtime cache from the official local
Feather files in the repository root:

```bash
./.venv312/bin/malecns-realtime-cache \
  --data-dir data/raw \
  --output-dir data/runtime/malecns-realtime-3hop
```

The adapter encodes each embodied sensor frame into exact MaleCNS sensory IDs,
advances one persistent Brian2 runtime per connected fly ID, and decodes that
window's `spikeRates`/`spikeCounts` into the normalized `FlightCommand` through
`FlightMotorDecoder`. The browser starts eight independent agents named
`fly-001` through `fly-008`; there is no special A/B pair. Manual flight is
fully local and applies only to the selected fly for debugging. If the cache is
absent, MaleCNS mode returns zero decoded flight drive and reports the missing
source instead of fabricating spikes. See `../docs/SWARM_ARCHITECTURE.md` and
`../docs/LIVE_CNS_LOOP.md`.

The browser sends each numbered fly's compact brain frame at 2 Hz by default.
Set
`VITE_BRAIN_UPDATE_HZ` when testing a different cadence; this is a transport
cadence choice, not a neural-parameter change.

## Controls

`W/S` pitch, `A/D` yaw, `Q/E` roll, `Shift` increases thrust, and `Ctrl`
decreases thrust/descends. `M` toggles the selected numbered fly between
manual/MaleCNS mode. Camera keys are `1` free orbit, `2` follow, `3`
first-person, `4` side/debug, `5` token cinematic, and `6` auto director. In
free orbit, left-drag rotates, right-drag pans, and the mouse wheel zooms toward
the cursor. The top-right `INSPECT FLY` selector chooses any of the eight
agents; `FOCUS` centers the free camera on it. Follow and first-person views
use that same selected fly. Press `` ` `` to switch between the compact demo
surface and detailed debug surface, and `P` to toggle the performance/demo
post-processing preset. Press `V` to show or hide direction vectors, and `I`
to show or hide the selected fly's detailed sensory/CNS causal panel.

The renderer reconstructs Flybody's articulated abdomen, thorax, head, eyes,
antennae, halteres, legs, and wing assemblies while retaining `FlyBody`,
`FlySensors`, and `FlyActuators`. The current browser physics adapter is still
the existing rigid-body path until an optional MuJoCo pose server is attached.

The arena is intentionally restrained: an invisible bounded flight volume, a
readable floor, three differentiated coin piles, and two locally bundled CC0
context props. All eight visible agents use the same canonical Flybody XML/OBJ
source; no decorative fallback swarm is created. Habitat particles and fly
trails use pooled GPU buffers.

The fly is rendered at an explicit 12x inspection magnification because its
physical body is millimetre-scale. This does not alter positions, collisions,
sensors, or telemetry.

At startup, all eight agents begin in a deterministic distant launch formation.
Their movement is not a hidden path to a selected coin. Each body samples its
own local vision, odor, motion, and contact state, sends compact sensor
summaries to its own `fly-NNN` brain stream, receives that fly's latest Brian2
command, and integrates the command through its own `FlyBody`. If the selected
MaleCNS DN populations are quiet, the correct result is a neutral command and
no autonomous token-directed movement. The selected causal panel exposes the
left/right eye summaries, odor, contact state, exact encoded `R8d`/`ORN_DA1`
counts, and the returned DN/command stage.

Use `NEUTRAL`, `DIFFERENT SIGNALS`, and `RELOCATED COINS` to change only the
habitat sensory fields. These are mock habitats, not live token data. `LIVE
GRAPH` uses the optional provider-neutral market adapter. The Graph
configuration requires both a pool ID and the represented token address so
buy/sell direction is resolved relative to that token. See
`../docs/MARKET_SIGNAL_ARCHITECTURE.md`.
It also shows the SENSORY -> CNS -> descending activity -> FLIGHT COMMAND
pipeline and a downloadable JSON flight log. The sensor contract
intentionally excludes food, target, and obstacle coordinates. Sensor details
and provenance are documented in `../docs/SENSORY_WORLD.md`.
