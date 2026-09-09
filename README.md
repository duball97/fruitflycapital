# fly-social-cns

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

`malecns.flybody.MuJoCoFlybody` accepts Flybody's native actuator vector and
returns its pose. A FlightCommand-to-native-joint mapping is intentionally not
invented; the browser remains on the existing actuator-compatible adapter
until that mapping is scientifically specified.

Bootstrap for a biologically grounded two-male-*Drosophila* CNS project.

It loads and queries the official Janelia/Google MaleCNS v1.0 dataset
(`male-cns:v1.0`) through either neuPrint or local Apache Feather files and
provides a CPU Brian2 reference LIF model plus conservative sensory/motor
population registries. It does not implement learning, reinforcement
learning, or any direct Fly A → Fly B neural edge.

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

For the live one-fly MaleCNS loop, build the small, reproducible runtime cache
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
realtime cache present, the adapter owns one persistent Brian2 runtime for
Fly A and returns live spike counts/rates; without it, the adapter stays
neutral and reports that source explicitly. Manual flight remains fully live.
See [docs/LIVE_CNS_LOOP.md](docs/LIVE_CNS_LOOP.md) and
[docs/FLIGHT_MOTOR_MAPPING.md](docs/FLIGHT_MOTOR_MAPPING.md) for evidence and
limitations.
The embodied sensor contract is documented in
[docs/SENSORY_WORLD.md](docs/SENSORY_WORLD.md).

## NeuroSwarm synthetic habitats

The current next milestone is implemented in the frontend as one active
MaleCNS candidate (Fly A), one stationary/off comparison body (Fly B), and
three synthetic `TokenHabitat` instances.
Each habitat displays two small canonical Flybody swarm members; the two
foreground bodies remain separate from the active CNS candidate. The habitats expose
only physical proxies—visual brightness/motion, swarm activity, attractive
odor, and aversive danger. They do not call APIs or
represent real tokens. Switch among `A · OFF`, `B · DIFFERENT`, and `C ·
SWAPPED` in the scene to inspect the sensory changes.

Run the deterministic headless sensory audit with:

```bash
MPLBACKEND=Agg PYTHONPATH=src python experiments/token_habitat_experiments.py \
  --output-dir results/token_habitats --seed 20260909
```

It writes `summary.json`, `telemetry.parquet`, `trajectory.csv`, a sensory
exposure plot, and a report. The visual habitat members are not CNS agents.
The live browser experiment is evidence of the embodied input-to-Brian2-to-
decoder path when the cache and adapter are running, but it is not evidence
that the MaleCNS has learned or chosen token-directed behavior.
