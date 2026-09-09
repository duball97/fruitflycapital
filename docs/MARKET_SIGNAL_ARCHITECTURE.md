# Market signal architecture

Fruit Fly Capital uses market data as an environmental source for the fly
world. It is not a direct brain command channel and it is not a claim that a
market metric has a biological equivalent.

## Data flow

```text
GraphProvider
    |
    v
RawTokenObservation
    |
    v
TokenSignalEngine
    |
    +--> TokenState
    |      market / flow / liquidity / holders / security / social / lore
    |
    +--> Signal[]
           value / normalized / importance / valence / confidence / freshness
    |
    v
HabitatEncoder
    |
    v
PhysicalHabitatState
    |
    v
Three.js habitat -> embodied fly sensors -> MaleCNS input
```

`GraphProvider` is one provider implementation. The habitat model does not
depend on The Graph's response shape, and no raw market fields are forwarded
to a fly. A future DexScreener, holder, security, or social provider should
produce another `RawTokenObservation` or a domain-specific observation that
is merged with explicit provenance before encoding.

## TokenState

The Python model is in
[`src/malecns/market/models.py`](../src/malecns/market/models.py). It contains:

- `market`: pair-relative price, and USD volume over 5 minutes, 15 minutes,
  and 1 hour;
- `flow`: token-relative buy/sell counts and USD amounts over 5 minutes, flow
  imbalance, transaction velocity, and transaction acceleration;
- `liquidity`: pool TVL in USD, change since the previous poll, and the 1-hour
  volume/liquidity ratio;
- `holders`, `security`, `social`, and `lore`: explicit domain sections whose
  status is currently `unavailable` because this provider does not supply
  those facts;
- `signals`: the derived, provenance-bearing signal list;
- `provenance`: provider, pool, represented token, and observation time.

An unavailable field is not a zero measurement. It is a statement that this
provider has not observed that domain. The encoder therefore does not invent
holder growth, contract safety, sentiment, or narrative catalysts.

## Signal contract

Every `Signal` includes:

| Field | Meaning |
| --- | --- |
| `value` | The derived value in its native units, such as USD or a count. |
| `normalized` | A bounded 0..1 representation used by the habitat encoder. |
| `importance` | How much this signal is allowed to contribute to an encoded habitat field. |
| `valence` | Signed interpretation where one is positive and minus one is negative; magnitude-only signals are neutral. |
| `confidence` | Confidence that the provider supplied enough data for this value. |
| `freshness` | Freshness at observation time, currently 1 for a successful poll. |
| `source` | The provider that produced the observation, currently `the-graph`. |
| `observedAtMs` | Provider observation time. |

The current signal list is intentionally small and inspectable:

```text
market.volume5mUsd
market.volume15mUsd
market.volume1hUsd
flow.buyCount5m
flow.sellCount5m
flow.buyUsd5m
flow.sellUsd5m
flow.imbalance
flow.txVelocity5m
flow.txAcceleration
liquidity.usd
liquidity.deltaUsd
liquidity.volumeLiquidityRatio1h
```

## Graph metrics

The provider requests up to 1 hour of swaps, sorted newest first, and the
signal engine derives all windows from the returned observations. For a poll
time `t`, a window of duration `d` contains swaps in `[t-d, t]`.

- `volume5m`, `volume15m`, and `volume1h` are sums of absolute `amountUSD`.
- `buyCount5m` and `sellCount5m` count swaps classified for the represented
  token.
- `buyUsd5m` and `sellUsd5m` sum the absolute USD amount of those swaps.
- `flowImbalance` is `(buyUsd5m - sellUsd5m) / (buyUsd5m + sellUsd5m)`, or
  zero when there were no classified trades.
- `txVelocity5m` is the number of unique transaction IDs in the 5-minute
  window divided by 5, giving transactions per minute.
- `txAcceleration` is the current 5-minute transaction velocity minus the
  preceding 5-minute interval's velocity.
- `liquidityDeltaUsd` is current pool TVL minus the previous observed TVL. It
  is unavailable on the first poll.
- `volumeLiquidityRatio1h` is 1-hour volume divided by current pool TVL, or
  zero when TVL is not positive.

### Buy/sell direction

The habitat configuration must include `tokenAddress`. The provider verifies
that it is one of the pool's `token0` or `token1` addresses. Classification
then uses the corresponding Uniswap pool amount: a negative pool balance
delta means the pool sent the represented token out (buy), and a positive
delta means the pool received it (sell). This follows the official Uniswap v3
pool action interface and event definitions:

- [Uniswap v3 pool actions](https://github.com/Uniswap/v3-core/blob/main/contracts/interfaces/pool/IUniswapV3PoolActions.sol)
- [Uniswap v3 pool events](https://github.com/Uniswap/v3-core/blob/main/contracts/interfaces/pool/IUniswapV3PoolEvents.sol)

The old shortcut of always interpreting `amount0` is therefore not used.

The Graph client uses a GraphQL `first` limit, timestamp filter, and
timestamp ordering. The provider default is 1,000 swaps over the 1-hour
lookback; these are query bounds, not a claim that the pool had only 1,000
swaps. See [The Graph GraphQL API documentation](https://thegraph.com/docs/en/subgraphs/querying/graphql-api/).

## Normalization and assumptions

The following are `OUR_ASSUMPTION`, not MaleCNS data or published Shiu model
parameters:

- USD volume normalization uses tanh scales of $10,000 for 5 minutes,
  $25,000 for 15 minutes, and $100,000 for 1 hour;
- transaction count normalization uses a scale of 10 transactions;
- transaction velocity and acceleration use a scale of 10 transactions per
  minute;
- liquidity normalization uses a $1,000,000 scale;
- ratio normalization uses a scale of 1.0;
- successful observations currently receive confidence 1 and freshness 1;
- `HabitatEncoder` turns activity, transaction velocity, liquidity, and flow
  valence into brightness, motion, odor, particle activity, and a bounded
  danger proxy.

The last item is an environmental visualization proxy. In particular,
`danger` is not a security audit and must not be presented as honeypot or
contract-risk truth. Security signals will only be added after a provider
supplies them with their own provenance.

The encoder does not directly compute thrust, yaw, pitch, or roll. The output
is physical habitat stimulation; the existing fly sensor and MaleCNS pathway
remains the only route from the habitat to a motor command.

## Provider roadmap

The next providers should be additive rather than changing the Graph layer:

1. DexScreener for pair metadata and independently sourced market context;
2. holder and contract-security providers for their explicit domains;
3. social and lore providers for narrative observations.

Each addition must preserve source, observed time, confidence, and the
distinction between observed data, published assumptions, and project
assumptions. Until then, the live Graph mode is limited to onchain pool,
swap, flow, and liquidity signals.
