from malecns.fund.chain_client import ChainBalance, FakeChainClient
from malecns.fund.execution import ExecutionEngine, FakeExecutionAdapter
from malecns.fund.ledger import FundLedger
from malecns.fund.models import TradeIntent
from malecns.fund.portfolio import PortfolioEngine
from malecns.fund.privy_client import FakePrivyClient, PrivyConfig
from malecns.fund.nav_reporter import FundNavReporter
from malecns.fund.valuation import FakeValuationProvider
from malecns.fund.wallet import RpcWalletClient, WalletSnapshot


def test_ledger_deduplicates_external_events_and_records_trade():
    ledger = FundLedger(":memory:")
    assert ledger.append_event("Deposit", {"amount": 100}, source="vault", external_id="0x1")
    assert ledger.append_event("Deposit", {"amount": 100}, source="vault", external_id="0x1") is None
    ledger.record_trade({"chain_id": 84532, "token_in": "USDC", "token_out": "TOKEN", "amount_in": "5", "round_id": "12", "neuroswarm_decision_id": "d1"})
    assert ledger.rows("trades")[0]["round_id"] == "12"


def test_portfolio_is_chain_aware_and_reconciles():
    ledger = FundLedger(":memory:")
    ledger.record_deposit(asset="USDC", amount=100, shares=100)
    ledger.upsert_position(chain_id=84532, token_address="0xabc", symbol="USDC", amount=100, cost_basis_usd=100)
    ledger.upsert_position(chain_id=1, token_address="0xabc", symbol="USDC", amount=2, cost_basis_usd=2)
    prices = FakeValuationProvider({(84532, "0xabc"): 1, (1, "0xabc"): 1})
    snapshot = PortfolioEngine(ledger, prices).snapshot()
    assert snapshot.nav_usd == 102
    assert len(snapshot.positions) == 2
    assert PortfolioEngine(ledger, prices).reconcile({(84532, "0xabc"): 100}, {(84532, "0xabc"): 99})["status"] == "discrepancy"


def test_dry_run_never_calls_execution_adapter_and_live_is_gated():
    adapter = FakeExecutionAdapter()
    intent = TradeIntent("token", "buy", "USDC", "TOKEN", "5", 84532, .1, .8, "test")
    dry = ExecutionEngine("dry-run", adapter=adapter).execute(intent)
    assert dry.status == "proposal_only" and not adapter.calls
    live = ExecutionEngine("live", adapter=adapter, live_confirmed=False).execute(intent, explicit_confirmation=True)
    assert live.status == "blocked" and not adapter.calls
    testnet = ExecutionEngine("testnet", adapter=adapter).execute(intent)
    assert testnet.status == "simulated" and len(adapter.calls) == 1


def test_fake_chain_client_does_not_merge_same_address_across_chains():
    items = [ChainBalance(1, "0xwallet", "0xasset", 1), ChainBalance(84532, "0xwallet", "0xasset", 2)]
    client = FakeChainClient(items)
    assert [x.amount for x in client.get_balances(1, "0xwallet", ["0xasset"])] == [1]
    assert PrivyConfig(app_id="a", app_secret="b").configured


def test_buy_and_partial_sell_update_cost_basis_and_realized_pnl():
    ledger = FundLedger(":memory:")
    engine = PortfolioEngine(ledger, FakeValuationProvider())
    engine.apply_trade(chain_id=84532, token_in="USDC", token_out="TOKEN", amount_in=10, amount_out=100, usd_value=10, symbol_out="TOKEN")
    realized = engine.apply_trade(chain_id=84532, token_in="TOKEN", token_out="USDC", amount_in=40, amount_out=6, usd_value=6, symbol_out="USDC")
    ledger.record_trade({"chain_id": 84532, "token_in": "TOKEN", "token_out": "USDC", "amount_in": "40", "amount_out": "6", "usd_value": 6, "realized_pnl_usd": realized, "status": "filled"})
    token = next(row for row in ledger.rows("positions", limit=10) if row["token_address"] == "TOKEN")
    assert token["amount"] == 60 and token["cost_basis_usd"] == 6
    assert realized == 2
    assert engine.snapshot().realized_pnl_usd == 2


def test_nav_reporting_and_privy_fake_are_explicitly_gated():
    reporter = FundNavReporter("dry-run")
    assert reporter.report(55).status == "preview"
    assert reporter.report(55, explicit_confirmation=False).status == "preview"
    privy = FakePrivyClient()
    try:
        privy.send_transaction("fake-wallet", {"to": "0x1"}, caip2="eip155:84532")
    except PermissionError:
        pass
    else:
        raise AssertionError("fake Privy client must require confirmation")


def test_wallet_snapshot_keeps_gas_reserve_out_of_tradeable_balance():
    snapshot = WalletSnapshot(4663, "0xB2B6710B85BfFF84b68aA4a91e78532f4FA726a9", 4_500_000_000_000_000)
    assert float(snapshot.native_balance_eth) == 0.0045
    assert snapshot.available_native_wei == 2_500_000_000_000_000
    assert snapshot.as_dict()["availableToTrade"] == 0.0025


def test_rpc_wallet_rejects_chain_mismatch_without_signing():
    client = RpcWalletClient("https://example.invalid", "0xB2B6710B85BfFF84b68aA4a91e78532f4FA726a9", expected_chain_id=4663)
    client.call = lambda method, params: "0xb626" if method == "eth_chainId" else "0x0"  # type: ignore[method-assign]
    try:
        client.snapshot()
    except RuntimeError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("wallet must reject an RPC on the wrong chain")
