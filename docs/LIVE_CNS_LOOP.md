# Live one-fly MaleCNS loop

This is the first embodied integration milestone. It makes the data path real
for one browser fly without claiming that a desired behavior has emerged.

```text
Three.js FlySensors
  -> R8d / ORN_DA1 stimulation entries
  -> persistent Brian2 MaleCNS runtime
  -> actual cached-window spike counts and rates
  -> FlightMotorDecoder selected DN rates
  -> FlyActuators
  -> FlyBody rigid-body physics
  -> changed pose and new sensor frame
```

Fly A is the active candidate. Fly B remains rendered with the same canonical
Flybody body but uses an `OFF` stationary controller and sends no brain input.
The nine small flies at the coin piles are visual swarm members only; they do
not each have a MaleCNS copy.

## Starting it

From the repository root, with the official local Feather files present:

```bash
./.venv312/bin/malecns-realtime-cache \
  --data-dir data/raw \
  --output-dir data/runtime/malecns-realtime-3hop
./.venv312/bin/python -m malecns.brain_server --host 127.0.0.1 --port 8765
```

In another terminal:

```bash
cd frontend
npm run dev
```

If the cache is absent, the server stays usable for manual mode but reports
`decoder-without-live-provider` and returns neutral CNS commands.

## What is observed versus assumed

Observed and preserved:

- official MaleCNS v1.0 body IDs and annotations;
- official weighted edge direction and raw synapse weights;
- exact mapped R8d, ORN_DA1, JO-B1_b, and flight-output populations;
- actual Brian2 spike counts/rates from each fixed runtime window.

Published methodology retained:

- Shiu-style LIF equation and parameters;
- external Poisson drive semantics;
- Brian2 state evolution and synaptic delay/decay model.

Our explicit boundary assumptions:

- only the source-reachable three-hop path from mapped sensory IDs to
  annotated flight outputs is stepped interactively;
- visual mean luminance and center odor concentration are converted to
  `150 Hz * bounded signal` input rates;
- optic flow, aversive odor, wind, gravity, and contact remain observed but
  unencoded until a defensible MaleCNS mapping is established;
- decoder normalization and the yaw sign remain project-level actuator
  conventions.

The cache is not a replacement for the full official graph. The local source
contains 211,577 annotated neurons and 151,856,684 weighted edges. The cache
manifest records its 6,641 nodes, 65,110 retained edges, source/target IDs,
raw total weight, and three-hop boundary.

## Current scientific result

The reproducible smoke run is `experiments/live_malecns_smoke.py` and writes
`results/live_malecns_smoke.json`. With seed 17 and four 50 ms windows:

- neutral produced zero spikes and a neutral command;
- visual-left and visual-right produced upstream activity, but no selected
  flight-DN activity reached the decoder in this bounded graph;
- odor-only produced nonzero turning-DN activity and a nonzero yaw command;
- DNg02 wing-amplitude activity was zero in all four cases, so decoded thrust
  was zero.

This is a genuine partial success and a genuine flight failure: the live
sensor → Brian2 → DN → decoder path works, but sustained autonomous flight is
not demonstrated. The next investigation is whether a scientifically
defensible longer MaleCNS path or additional annotated flight population can
be justified. No motor gain, lift command, or target-following rule should be
added merely to make the fly move.
