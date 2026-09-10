# 🪰 FRUIT FLY CAPITAL

### What happens when a swarm of fruit-fly brains gets control of a crypto wallet?

**We turn the crypto market into an ecosystem—and let biology decide where to go.**

Fruit Fly Capital's multi-agent system is called **NeuroSwarm**. It combines the
official MaleCNS v1.0 connectome, Brian2 neural dynamics, the canonical
TuragaLab/Flybody body, Three.js, The Graph, and a quote-only Uniswap boundary.

```text
market data → sensory world → MaleCNS circuits → body movement
             → population behavior → guarded trade intent
```

The flies never receive a token symbol, chart, price recommendation, target
coordinate, or direct command such as “go to TOKEN-X”. Market information is
translated into environmental signals—light, motion, odor, and danger—and is
then sensed through the embodied loop.

## Current reality

The current interactive default is a **16-brain pilot**, not 100 completed
full-CNS simulations. The browser renders five canonical Flybody views per
brain by default, so 16 brains produce 80 visible flies. Each numbered primary
agent (`fly-001` through `fly-016`) has its
own Flybody pose, sensor frame, actuator state, and server-side Brian2 runtime
identity/seed. The connectome topology and model parameters are shared as
immutable configuration; membrane state, spikes, history, and RNG state are
not shared. Four additional bodies per primary are render-only followers: they
share the primary actuator intent with small deterministic spacing and timing
variation, but do not sense, run a brain, or add votes.

The realtime adapter currently runs a documented source-reachable three-hop
MaleCNS circuit of roughly 6,641 neurons and 65,110 retained weighted edges per
runtime. It does not step the full 211,577-neuron, 151,856,684-edge graph for
each fly. The UI therefore separates `AGENTS`, `CNS RUNTIMES`, `CNS ACTIVE`,
`MOVING`, and `DRIVE` instead of implying that neural activity equals movement.

The literal MaleCNS decoder has evidence-constrained turning/flight readouts,
but the live DNg02 wing-amplitude path has not yet produced sustained thrust in
the realtime smoke result. The browser therefore starts in an explicitly
labelled `PREVIEW` driver so the Flybody population is visibly flying while
the neural result remains inspectable. Preview movement uses only each fly's
local eye/antenna/optic-flow/contact observations and the same
`FlyActuators -> FlyBody` interface; it does not receive token coordinates or
issue a hidden “go to coin” command. Set `VITE_FLIGHT_DRIVER=malecns` to run
the literal decoded neural command, where a neutral command is still an
honest possible result until a validated lift pathway is established.

The population size is configurable with `frontend/.env`:

```env
VITE_SWARM_SIZE=16
VITE_BODIES_PER_BRAIN=5
```

Values from 1 to 100 are accepted, but 100 should be treated as a staged
benchmark target. One independent Brian2 runtime per fly at the current cache
size is a substantial CPU/RAM workload; a fleet scheduler or compiled/vector
backend is required before claiming that 100 independent brains run smoothly.

The canonical rendered Drosophila body is TuragaLab/Flybody's MuJoCo model,
loaded from `flybody/fruitfly/assets/fruitfly.xml` and its referenced OBJ
assets. The browser uses Three.js for visualization; MaleCNS remains the brain
and the current physics-backend boundary is documented in
`docs/FLYBODY_INTEGRATION.md`.

The vendored dependency is Apache-2.0 licensed. Do not replace it with a
random GLTF asset or silently call the placeholder fallback a canonical body.

An optional MuJoCo wrapper loads this exact XML without changing it. On macOS,
use an explicit Python 3.12 interpreter; a global `python` command may not be
installed, and the system `python3` may be too old for this project:

```bash
brew install python@3.12
PYTHON312="$(brew --prefix python@3.12)/bin/python3.12"
"$PYTHON312" -m venv .venv312
./.venv312/bin/python -m pip install -e '.[dev,physics,speed]'
cp .env.example .env
```

The Python brain server and market-report command automatically load this
repository-root `.env` for local development. Explicitly exported shell
variables take precedence. Restart the brain server after changing `.env`.

`malecns.flybody.MuJoCoFlybody` accepts Flybody's native actuator vector and
returns its pose. A FlightCommand-to-native-joint mapping is intentionally not
invented; the browser remains on the existing actuator-compatible adapter
until that mapping is scientifically specified.

## Deployment boundary

The Three.js client can be deployed to Vercel as a Vite site. Set Vercel's
project root to `frontend`, use `npm run build`, and publish `dist`. Set
`VITE_BRAIN_WS_URL` to a public `wss://` endpoint in the deployed environment;
the local `ws://127.0.0.1:8765` default only works on the developer's machine.

The current `malecns.brain_server` is a standalone, long-running WebSocket
process with an in-memory Brian2 runtime registry. It is not a Vercel Function
entrypoint and should run on a persistent Python host/container. Vercel's
Python runtime is suitable for HTTP Functions, but adapting this stateful brain
server to Vercel would require a Function/WebSocket entrypoint, externalized
runtime state, and a separate capacity plan. Keep Graph and Uniswap credentials
on that server; never expose them as `VITE_` variables.

Bootstrap for a biologically grounded MaleCNS *Drosophila* swarm project. The
product is Fruit Fly Capital / NeuroSwarm: biological agents in an onchain
market ecology.

It loads and queries the official Janelia/Google MaleCNS v1.0 dataset
(`male-cns:v1.0`) through either neuPrint or local Apache Feather files and
provides a CPU Brian2 reference LIF model plus conservative sensory/motor
population registries. It does not implement learning, reinforcement
learning, or any direct fly-to-fly neural edge.

## Setup

Use the project environment explicitly (the package requires Python >=3.10):

```bash
brew install python@3.12
PYTHON312="$(brew --prefix python@3.12)/bin/python3.12"
"$PYTHON312" -m venv .venv312
./.venv312/bin/python -m pip install -e '.[dev,physics]'
cp .env.example .env
```

Start the optional brain adapter from the repository root with:

```bash
./.venv312/bin/python -m malecns.brain_server --host 127.0.0.1 --port 8765
```

For the live MaleCNS loop, build the small, reproducible runtime cache
from the official local Feather files before starting the adapter:

```bash
./.venv312/bin/malecns-realtime-cache \
  --data-dir data/raw \
  --output-dir data/runtime/malecns-realtime-3hop
./.venv312/bin/python -m malecns.brain_server --host 127.0.0.1 --port 8765
```

The cache retains exact MaleCNS weighted paths from the mapped sensory IDs to
annotated flight-output IDs within a documented three-hop analysis boundary.
It is not a replacement for the full 211,577-neuron/151,856,684-edge source
graph; see [docs/LIVE_CNS_LOOP.md](docs/LIVE_CNS_LOOP.md).

Run the one-fly live smoke test after building the cache:

```bash
MPLCONFIGDIR=/tmp/malecns-mpl PYTHONPATH=src \
  ./.venv312/bin/python experiments/live_malecns_smoke.py
```

This reports actual neutral, lateralized-visual, and odor-only spike/DN
responses. It is a diagnostic result, not a claim that autonomous flight has
already succeeded.

The public neuPrint service requires a token for live queries. Put it in the
environment as `NEUPRINT_TOKEN`; never commit it.

## Official local data

The downloader accepts explicit file keys so the large connectivity table is
never fetched accidentally:

```bash
python -m malecns.download annotations neurotransmitters stats --output-dir data/raw
python -m malecns.download connectivity --output-dir data/raw  # approximately 1.1 GB
```

The loader recognizes the exact v1.0 filenames from the official download page,
and a single clearly named local variant for each file. Annotations and
connectivity are required; neurotransmitter and body-stats files are optional.

Run the validation report after the required files are present:

```bash
malecns-report --data-dir data/raw
```

The report prints loaded neuron and edge counts, total edge weight, observed
neurotransmitter and side distributions, and category counts only when an
exact `class`/`subclass` label is present. It does not infer sensory,
descending, or motor identity from names such as DN/MN.

## Python API

```python
from malecns import load_malecns_tables, query_neurons
from malecns.annotations import incoming_edges, outgoing_edges

neurons, edges = load_malecns_tables("data/raw")
right = query_neurons(neurons, side="right")
dn = query_neurons(neurons, type="DNge104")
outgoing = outgoing_edges(edges, dn["body_id"].tolist())
incoming = incoming_edges(edges, dn["body_id"].tolist())
```

For live access:

```python
from malecns.neuprint_client import MaleCNSClient

client = MaleCNSClient()
neurons = client.query_neurons(type="DNge104")
edges = client.connectivity(body_ids=neurons["body_id"].tolist(), direction="outgoing")
```

## Brian2 reference dynamics

After the complete connectivity Feather is available:

```python
from malecns.brain import BrainSimulation, LIFParameters

brain = BrainSimulation.from_malecns(
    "data/raw",
    parameters=LIFParameters.load("data/parameters/shiu-male-cns-v1.json"),
    seed=7,
)
brain.stimulate(body_ids=[10001], frequency_hz=150.0)
result = brain.run(duration_ms=500.0)
print(result.spikes)
print(result.firing_rates.sort_values("firing_rate_hz", ascending=False).head())
```

The default `unknown_sign="exclude"` policy uses only acetylcholine-positive
and GABA-negative edges. Ambiguous or missing transmitter signs are reported
and excluded from the Brian2 graph; raw edges remain available through the
`ConnectivityMatrix`. No edge-weight normalization is performed.

The reference demo is:

```bash
python experiments/connectome_propagation_demo.py
```

## Controlled 3-D flight experiments

The headless controlled-run harness is:

```bash
MPLCONFIGDIR=/tmp/malecns-mpl MPLBACKEND=Agg PYTHONPATH=src \
  python experiments/autonomous_flight_experiments.py \
  --output-dir results/single_fly_3d --seed 20260909
```

It runs visual stabilization, four visual target directions, odor-only flight,
and 60 seconds of free flight, writing compressed JSONL, Parquet telemetry,
plots, a trajectory CSV, configuration, and a numerical report. The current
rate-provider boundary is explicit: until a live Brian2 provider is attached,
the `malecns_connected` condition has neutral decoded motor output and is not
an autonomous MaleCNS result. See [results/single_fly_3d/REPORT.md](results/single_fly_3d/REPORT.md).

## Sensory/motor mapping status

Annotation-grounded sensory and descending registries are implemented in
`src/malecns/sensory/registry.py` and `src/malecns/motor/registry.py`.
The reproducible left/right visual audit is:

```bash
MPLBACKEND=Agg PYTHONPATH=src python experiments/lateralized_sensory_asymmetry.py
```

It retains official `R8d` → three-hop → `DNa01`/`DNa02`/`DNp09`/`DNp28`
paths, reports exact body IDs and spikes, and writes a plot under
`results/figures/`. It does not assign movement gains. Stop and dedicated
walking-state registries remain empty when MaleCNS v1.0 does not expose those
exact labels. See [docs/SENSORY_MOTOR_MAPPING.md](docs/SENSORY_MOTOR_MAPPING.md)
and [docs/MODEL_ASSUMPTIONS.md](docs/MODEL_ASSUMPTIONS.md).

## 3D fly world

The `frontend/` directory contains the Three.js/Vite embodied-world prototype.
It uses a 2 m x 1 m x 2 m arena, a 120 Hz rigid-body step, four camera modes,
manual keyboard flight, and a WebSocket actuator boundary for the Python
MaleCNS process. See [frontend/README.md](frontend/README.md) for launch
commands. `FlightMotorDecoder` provides the documented, rate-only
MaleCNS-to-actuator boundary for exact annotated flight populations. With the
realtime cache present, the adapter owns one persistent Brian2 runtime per
connected `fly-NNN` ID and returns live spike counts/rates; without it, the
adapter stays neutral and reports that source explicitly. Manual flight remains
fully live.
See [docs/LIVE_CNS_LOOP.md](docs/LIVE_CNS_LOOP.md) and
[docs/FLIGHT_MOTOR_MAPPING.md](docs/FLIGHT_MOTOR_MAPPING.md) for evidence and
limitations.
The embodied sensor contract is documented in
[docs/SENSORY_WORLD.md](docs/SENSORY_WORLD.md).

## Onchain habitat data

The optional `LIVE GRAPH` feed is deliberately layered:

```text
GraphProvider -> RawTokenObservation -> TokenSignalEngine -> Signal[]
              -> HabitatEncoder -> physical habitat fields -> fly sensors
```

`TokenState` keeps market, flow, liquidity, holders, security, social, and
lore as separate domains. Each derived signal carries its value, normalized
value, importance, valence, confidence, freshness, source, and observation
time. The current Graph provider supplies market/flow/liquidity only; missing
holder, security, social, and lore data remains explicitly unavailable. See
[docs/MARKET_SIGNAL_ARCHITECTURE.md](docs/MARKET_SIGNAL_ARCHITECTURE.md) for
metric definitions, provenance, and the planned provider boundaries.

## NeuroSwarm population pilot

The current milestone is a sixteen-brain population pilot rendered as eighty
canonical Flybody bodies. Each primary has its own body, sensor frame,
actuator state, unique `fly-NNN` brain ID, and server-side RNG stream. Four
render-only followers are attached to each primary; they do not sense, create
brain runtimes, or add consensus votes. The three synthetic `TokenHabitat`
instances expose
only physical proxies—visual brightness/motion, attractive odor, and aversive
danger. They do not call APIs or represent real tokens. Switch among
`NEUTRAL`, `DIFFERENT SIGNALS`, and `RELOCATED COINS` in the scene to inspect
the sensory changes.

Run the deterministic headless sensory audit with:

```bash
MPLBACKEND=Agg PYTHONPATH=src python experiments/token_habitat_experiments.py \
  --output-dir results/token_habitats --seed 20260909
```

It writes `summary.json`, `telemetry.parquet`, `trajectory.csv`, a sensory
exposure plot, and a report. The live browser experiment is evidence of the
embodied input-to-Brian2-to-decoder path when the cache and adapter are
running, but it is not evidence that the MaleCNS has learned or chosen
token-directed behavior. See [docs/SWARM_ARCHITECTURE.md](docs/SWARM_ARCHITECTURE.md)
for the per-fly causal chain and runtime-capacity interpretation.

## Why the flies do not go to the boxes yet

The cardboard box and trash cans are optional local CC0 **context props**. They
are not token habitats, do not emit the attractive odor field, and are not
targets. The three colored coin piles are the synthetic token habitats used by
the current prototype.

The movement path is intentionally:

```text
habitat light / motion / odor
        ↓
embodied FlySensors
        ↓
exact MaleCNS sensory IDs
        ↓
Brian2 spikes and annotated descending activity
        ↓
FlightMotorDecoder
        ↓
FlyActuators → FlyBody
```

There is currently no validated ordinary-forward-flight output from the
selected realtime MaleCNS path. When its thrust readout is quiet, the correct
result is that the fly stays put. Adding a direct “go to the box/coin” force
would make the demo look active but would invalidate the experiment. See
[`docs/FLIGHT_MOTOR_MAPPING.md`](docs/FLIGHT_MOTOR_MAPPING.md) and
[`docs/SWARM_ARCHITECTURE.md`](docs/SWARM_ARCHITECTURE.md).

## Next steps

1. Validate a scientifically defensible MaleCNS flight-output path, including
   sustained lift/forward movement and stable turning, first for one fly.
2. Replace synthetic habitats with configured token observations from The
   Graph, preserving signal provenance and unavailable fields.
3. Benchmark 16, 32, and then 100 independent runtimes. Add scheduling or
   vectorized/compiled execution before making 100-agent realtime claims.
4. Add measured swarm entry, exit, dwell, approach, avoidance, and persistence
   metrics. These metrics—not a single fly—must produce any future TradeIntent.
5. Add fly-to-fly perception through the world, then a risk guard around
   Uniswap quote/calldata generation. Transaction broadcasting remains a later,
   separately controlled step.

## Scientific integrity

This project does not train the connectome with gradient descent or
reinforcement learning, add Fly A → Fly B neural edges, or silently modify
synaptic weights to obtain a desired behavior. Observed MaleCNS data, published
model assumptions, and project assumptions are separated in
[`docs/MODEL_ASSUMPTIONS.md`](docs/MODEL_ASSUMPTIONS.md). The project is an
experimental research/hackathon prototype, not financial advice or a validated
trading strategy.
