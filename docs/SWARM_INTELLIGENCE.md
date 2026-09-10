# Swarm Intelligence and Fund Decision Boundary

Fruit Fly Capital now has an explicit population-level decision pipeline:

```text
primary CNS body telemetry
        ↓
SwarmObserver
        ↓
temporal behavior summaries per habitat
        ↓
behavior TradeIntent events (buy on dwell, sell on departure)
        ↓
TemporalConsensusEngine
        ↓
HabitatConviction
        ↓
PortfolioAllocator
        ↓
PortfolioTarget
        ↓
TradeIntent (only with explicit route + current holdings)
        ↓
RiskGuard
        ↓
proposal-only fund boundary
```

## What is measured

Only the sixteen independent CNS agents count. The four render-only bodies
attached to each CNS are never valid inputs to `SwarmObserver` and never add
votes. For each CNS/habitat pair the observer records visits, approach
episodes, departures, dwell time, repeat visits, bounded distance history,
contact time, local congregation, and dwell persistence.

An approach is a decreasing-distance episode while the agent is outside the
habitat. A visit begins when distance enters the habitat radius. A departure is
the corresponding exit. Dwell time is integrated only across telemetry samples
whose gap is at most two seconds, so reconnects cannot manufacture dwell.

The browser and server observers also emit a bounded behavioral event stream:

- `buy` means the same primary CNS agent reached contact, was grounded, and
  remained there for at least 0.6 seconds;
- `sell` means that visit subsequently departed;
- neither event contains a token address, amount, wallet, or transaction call.

These are behavioral proposals for the fund layer, not filled trades. The
execution seam remains proposal-only. The browser-side
`TradeExecutionBoundary` exposes the future custody seam but currently only
returns a `proposal_only` record; it cannot connect, sign, or broadcast.

## Why it is temporal

The consensus engine uses visit coverage, sustained dwell, repeat visits, low
departure rate, persistence, and congregation. It does not select a market
from a single-frame count. Its weights are `OUR_ASSUMPTION` configuration and
are returned with each conviction's evidence for auditability.

## Portfolio and execution safety

The allocator produces target weights only. Default policy assumptions are a
10% cash reserve and an 18% maximum position. The risk guard checks those
limits and evidence confidence. These are fund-policy assumptions, not
biological parameters.

Financial `TradeIntent` objects are emitted only when the caller supplies an
explicit token route and current portfolio weights. The behavioral event stream
is separate: it records what a CNS body did, while the financial pipeline still
decides whether a route, amount, and target-weight change are allowed. The
observer never guesses token addresses or amounts from a habitat label.

The current result is explicitly `proposal_only`. No Privy signer, wallet,
private key, or transaction broadcaster is present. Uniswap remains a
quote/unsigned-calldata boundary. Any future transaction path must show the
asset, amount, chain, recipient, gas estimate, and risk decision and require
explicit human approval before signing or broadcasting.

## Input boundary

The browser may send body positions, habitat distances, contact state, and
agent IDs to the observer for measurement. It must continue sending sensory
signals—not token IDs, target coordinates, or portfolio recommendations—to
the MaleCNS runtime.
