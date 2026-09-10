# Fruit Fly Capital / NeuroSwarm — project status

Updated: 2026-09-10

This document separates what is implemented from what is demonstrated. A
moving fly in the browser is not automatically evidence that the MaleCNS is
driving it, so the UI and this report keep those claims separate.

## What exists now

### Biological agents

- The structural source is the official MaleCNS v1.0 dataset, with the
  published Shiu-style LIF reference adapted to the available MaleCNS graph.
- The browser creates 16 primary agents by default: `fly-001` through
  `fly-016`.
- Each primary has its own body state, sensors, actuator state, controller,
  brain ID, trajectory, and server-side runtime key.
- Each primary has four render-only followers by default. The visual population
  is therefore 80 Flybody meshes, but the scientific population is 16 CNS
  agents. Followers do not sense, run Brian2, vote, or create trades.
- `VITE_SWARM_SIZE` can be set from 1 to 100, but 100 full realtime Brian2
  runtimes has not been benchmarked or claimed as supported.

### Neural runtime

- Python exposes one persistent realtime runtime per `fly-NNN` over WebSocket.
- The interactive runtime currently uses a bounded three-hop MaleCNS subgraph,
  approximately 6,641 neurons and 65,110 weighted edges per runtime, rather
  than the complete CNS graph. This is an explicit performance boundary.
- The browser now exposes a **NEURAL TRACE** panel in `SHOW DETAILS`. It shows
  the exact output origin, recent spike-window activity, selected descending
  activity, and the decoded actuator command.
- The canonical proof label is `LIVE BRIAN2 → DECODER`. `PREVIEW → ACTUATOR
  (NOT NEURAL)` is deliberately labelled as non-neural.
- The current MaleCNS path has not established sustained, validated ordinary
  flight output. A neutral command in MaleCNS mode is therefore a real result,
  not a rendering failure. The preview driver exists only to test the body and
  sensor loop while this biological gap remains.

### Body and world

- The renderer targets TuragaLab Flybody's canonical XML/OBJ body hierarchy.
- This checkout currently contains a placeholder under
  `frontend/public/models/flybody`; the actual Flybody asset bundle is not
  present here. If the assets are not installed locally, the renderer reports
  fallback status and cannot honestly be called canonical in that run.
- The room has an explicit 2 m × 2 m × 1 m physical volume, a floor, three
  token habitats, simple odor fields, visual sampling, contact sampling, and
  pooled habitat particles.
- The habitats are token piles, not trash cans or arbitrary targets. Their
  brightness, motion, odor, risk, rings, beacon, and particles come from the
  provider-neutral `TokenState`/signal model or the documented fixture.

### Market and fund boundary

- The Graph and DexScreener are market-data providers; they do not directly
  steer a fly or choose a trade.
- The provider-neutral path is raw observation → normalized signals → habitat
  encoder → sensory exposure → CNS/runtime → swarm observations.
- The swarm layer records visits, approaches, departures, dwell, persistence,
  and congregation before producing a temporal conviction proposal.
- The fund layer contains a Foundry vault, an append-only SQLite ledger,
  portfolio/NAV reporting, risk gates, Privy REST integration, and Uniswap
  quote/calldata preparation.
- Execution defaults to dry-run. Live signing requires configured wallet and
  policy controls plus an explicit confirmation. No private key belongs in the
  repository or browser bundle.

## How to verify that the brain is guiding a fly

Use one selected primary agent and click `SHOW DETAILS`.

| Evidence | What it proves | What it does not prove |
|---|---|---|
| `LIVE BRIAN2 → DECODER` | The latest command came from the live Brian2 adapter source | That the biological pathway is complete or validated |
| Nonzero `SPIKES` in NEURAL TRACE | A returned MaleCNS window contained spikes | That those spikes caused the body command |
| Nonzero `DN PEAK` | A selected descending population was active | That it is a validated forward-flight pathway |
| `COMMAND` and body velocity change after the returned window | Timing consistency between neural output and motion | Causal proof by itself |
| Same seed, `MALECNS` versus `PREVIEW`/`OFF` | A controlled ablation comparison | A successful result if both remain neutral |
| Downloaded selected-fly log | A replayable chain of sensors → IDs → spikes/DN → command → pose | That missing data should be filled with guesses |

The strongest practical audit is a source-ablation test:

1. Run the same seed with `OFF`, `PREVIEW`, and literal `MALECNS`.
2. Record sensor frames, stimulation body IDs, spike counts/rates, DN rates,
   commands, and pose for each run.
3. Confirm the MaleCNS run has `source=brian2-malecns-v1-realtime-3hop`.
4. Compare the command and trajectory only after aligning the returned brain
   timestamps. A preview trajectory is not a neural result.

## What is still missing

1. A validated sustained MaleCNS sensory-to-flight/VNC pathway that produces
   lift, forward flight, and stable turning without a preview rule.
2. Full-connectome realtime scheduling or a compiled/vectorized backend for
   scaling toward 100 independent brains.
3. The actual Flybody XML and mesh assets in this checkout, plus a verified
   runtime asset report showing canonical loading.
4. A persistent production database and authenticated backend deployment for
   fund ledger/NAV data.
5. Deployed testnet vault addresses, configured Privy wallet/policy, and a
   human-approved live execution run. Quote/calldata is not a filled trade.
6. More market providers and rolling signal windows in production, with clear
   provenance and freshness handling.
7. Fly-to-fly sensory coupling through the environment, social experiments,
   and statistically meaningful swarm evaluations.

## Highest-value improvements

- First, finish the one-fly neural audit and publish the failed cases as well
  as successful ones.
- Second, add a replayable experiment runner so a sensor frame and brain output
  can be inspected without relying on a live browser session.
- Third, benchmark 16, 32, and 100 runtime schedules before choosing the final
  independent-brain count.
- Fourth, install and verify the canonical Flybody assets before visual polish.
- Fifth, make market snapshots and swarm observations durable before enabling
  any live fund execution.

## Good next demo features

- Click a habitat to show its signal provenance and freshness.
- Show a faint causal trail from the selected primary body to its five-body
  visual cohort, while counting the cohort as one CNS vote.
- Add experiment replay: same seed, same habitats, three driver modes,
  synchronized side-by-side traces.
- Add a “why this market?” panel that shows temporal visits/dwell/conviction,
  never a one-frame fly count.
- Add a visible safety state: `SIMULATION`, `QUOTE ONLY`, or `LIVE TESTNET`.

## Reproducible checks

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
cd frontend && npm run check && npm run build
cd ../contracts && forge test --offline -vvv
```

