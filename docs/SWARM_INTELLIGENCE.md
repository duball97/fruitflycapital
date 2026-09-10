# Swarm Intelligence and Fund Decision Boundary

Fruit Fly Capital now has an explicit population-level decision pipeline:

```text
primary CNS body telemetry
        ↓
SwarmObserver
        ↓
temporal behavior summaries per habitat
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

`TradeIntent` is emitted only when the caller supplies an explicit token route
and current portfolio weights. The observer never guesses token addresses,
amounts, or buy/sell direction from a habitat label. With no route/holdings
input—as in the browser demo—the intent list is correctly empty.

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
