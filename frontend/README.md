# MaleCNS Fly World frontend

This is a small Three.js/Vite client for the embodied fly-world prototype.
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

The adapter then encodes the embodied sensor frame into exact MaleCNS sensory
IDs, advances one persistent Brian2 runtime for each connected CNS fly, and
decodes that window's `spikeRates`/`spikeCounts` into the normalized
`FlightCommand` through `FlightMotorDecoder`. Fly A is the active candidate at
startup; Fly B is rendered as an OFF/stationary comparison body. Manual flight
is fully local and does not require the adapter. If the cache is absent,
MaleCNS mode returns zero decoded flight drive and reports the missing source
instead of fabricating spikes. See `../docs/LIVE_CNS_LOOP.md`.

The browser sends Fly A brain frames at 10 Hz by default. Set
`VITE_BRAIN_UPDATE_HZ` when testing a different cadence; this is a transport
cadence choice, not a neural-parameter change.

## Controls

`W/S` pitch, `A/D` yaw, `Q/E` roll, `Shift` increases thrust, and `Ctrl`
decreases thrust/descends. `M` toggles Fly A between manual/MaleCNS mode; Fly B
remains OFF. Camera keys are
`1` free orbit, `2` follow, `3` first-person, and `4` side/debug. In free orbit,
left-drag rotates, right-drag pans, and the mouse wheel zooms toward the cursor.
The top-right `CAMERA TARGET` buttons select Fly A, Fly B, or BOTH. Selecting a
target also focuses the free camera at inspection distance; follow and
first-person views use the selected fly (BOTH uses Fly A for those
single-body views). Press `V` to show or hide the large debug direction
vectors, and `I` to show or hide the detailed sensory/CNS panels.

The renderer reconstructs Flybody's articulated abdomen, thorax, head, eyes,
antennae, halteres, legs, and wing assemblies while retaining `FlyBody`,
`FlySensors`, and `FlyActuators`. The current browser physics adapter is still
the existing rigid-body path until an optional MuJoCo pose server is attached.

The arena is intentionally minimal: an invisible bounded flight volume, a
floor, and three differentiated coin piles. The visual swarm members use the
same canonical Flybody asset as the foreground flies.

The fly is rendered at an explicit 8x inspection magnification because its
physical body is millimetre-scale. This does not alter positions, collisions,
sensors, or telemetry.

At startup, the nine visual swarm bodies begin in a distant launch zone. Their
approach to the three coin piles is controlled by each pile's synthetic
attraction, activity, and danger parameters. This is separate from the active
foreground CNS candidate; the nine display members do not claim unimplemented
brains.

The scene contains one live CNS brain (Fly A), one OFF/stationary comparison
body (Fly B), and three synthetic `TokenHabitat` objects, each with three
canonical Flybody swarm members. Use `A · OFF`, `B · DIFFERENT`, and `C · SWAPPED` to
change only the habitat's physical sensory fields. These are mock habitats,
not live token data. The debug panel exposes the left/right eye summaries,
optic flow, attractive/aversive odor at the body and antennae, contact state,
and the exact encoded `R8d`/`ORN_DA1` body-ID counts.
It also shows the SENSORY -> CNS -> descending activity -> FLIGHT COMMAND
pipeline and a downloadable JSON flight log. The sensor contract
intentionally excludes food, target, and obstacle coordinates. Sensor details
and provenance are documented in `../docs/SENSORY_WORLD.md`.
