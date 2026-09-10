# Fruit Fly Capital fund / treasury boundary

This is a local, testnet, and dry-run architecture. It is not a regulated
public fund and does not claim trustless production NAV accounting.

```text
market → habitat → MaleCNS → swarm observation → allocation → TradeIntent
                                             ↓
                              RiskGuard → execution adapter → Privy policy
                                             ↓
                                      FundVault / portfolio ledger
```

## Contract

`contracts/src/FruitFlyFundVault.sol` is an explicit share-accounting vault:
USDC is the accounting asset and FFC shares have 18 decimals. The first
deposit establishes 1 USDC per share. Later deposits use the current integer
NAV/share. NAV is liquid vault USDC plus `reportedStrategyNavUsdc`.

The strategy treasury is one configured address; capital cannot be deployed to
an arbitrary recipient. Withdrawals use `REQUESTED → FUNDED → CLAIMED` and
escrow shares at request time. The request stores the NAV snapshot and fixed
USDC amount used for the eventual claim.

V1 uses an authorized offchain NAV reporter and is not a trustless production
fund accounting system. OpenZeppelin AccessControl, SafeERC20,
ReentrancyGuard, Pausable, ERC20, and Math are used; the contract is not
upgradeable and exposes no arbitrary-call function.

Run locally:

```bash
cd contracts
forge install OpenZeppelin/openzeppelin-contracts --no-git --shallow
forge install foundry-rs/forge-std --no-git --shallow
forge test --offline -vvv
anvil
PRIVATE_KEY=... FUND_USDC_ADDRESS=... FUND_CONTRACT_ADDRESS=... \
  forge script script/FundLifecycle.s.sol --rpc-url http://127.0.0.1:8545 --broadcast
```

For Base Sepolia, supply `FUND_RPC_URL`, `FUND_CHAIN_ID=84532`, a deployer
`PRIVATE_KEY`, and either `FUND_USDC_ADDRESS` or let the script deploy MockUSDC.
The repository never contains a private key and does not auto-deploy mainnet.

## Python fund package

`malecns.fund` owns the non-neural accounting boundary:

- `FundLedger` is sqlite3-backed and keeps raw fund events, deposits,
  withdrawals, trades, positions, NAV snapshots, balances, and metadata.
- `PortfolioEngine` calculates NAV, NAV/share, cash, deployed value, P&L,
  chain allocation, and reconciliation without Zerion.
- `CMCValuationProvider` is an optional price source; `FakeValuationProvider`
  is used by tests. Quotes retain source/provenance and are never balance proof.
- `PrivyClient` uses documented REST endpoints for listing/creating a wallet,
  balance reads, and `eth_sendTransaction`. It is server-side only.
- `ExecutionEngine` defaults to `dry-run`; it never signs or broadcasts there.
  Live execution requires both `FUND_LIVE_TRADING_CONFIRMED=true` and a
  separate explicit confirmation at the execution call.

Bootstrap only inspects configuration by default:

```bash
PYTHONPATH=src python -m malecns.fund.bootstrap_privy
PYTHONPATH=src python -m malecns.fund.bootstrap_privy --create
```

`--create` is an explicit wallet-creation operation. No secret is printed.
Configure a Privy policy before any testnet or live transaction and keep the
treasury address equal to the vault's `strategyTreasury`.

## Browser/API boundary

The existing `brain_server` accepts `fund_status_request`, `portfolio_request`,
and `trade_history_request`. It sends configuration, read-only accounting, and
audit records only; it never sends Privy secrets. `frontend/portfolio.html` is
a Vite multipage read-only dashboard. Empty or unconfigured state displays `—`
rather than fake production numbers.

The portfolio page can be deployed with the Three.js frontend to Vercel. The
stateful Python WebSocket brain/fund service must remain on a persistent
backend such as Render; Vercel only serves the static pages.
