"""Application service used by the WebSocket adapter and portfolio page."""
from __future__ import annotations
import os
from typing import Any, Iterable, Mapping
from .execution import ExecutionEngine
from .ledger import FundLedger
from .portfolio import PortfolioEngine
from .valuation import FakeValuationProvider

class FundService:
    def __init__(self, ledger: FundLedger, portfolio: PortfolioEngine, execution: ExecutionEngine) -> None: self.ledger, self.portfolio, self.execution = ledger, portfolio, execution
    @classmethod
    def from_env(cls) -> "FundService":
        ledger = FundLedger(os.getenv("FUND_DB_PATH", "data/fund/fund.db")); return cls(ledger, PortfolioEngine(ledger, FakeValuationProvider()), ExecutionEngine())
    def status(self) -> dict[str, Any]:
        return {"name": "Fruit Fly Capital", "mode": os.getenv("FUND_EXECUTION_MODE", "dry-run"), "chainId": os.getenv("FUND_CHAIN_ID") or "base-sepolia", "contractAddress": os.getenv("FUND_CONTRACT_ADDRESS"), "treasuryAddress": os.getenv("PRIVY_WALLET_ADDRESS"), "accountingAsset": "USDC", "security": {"walletProvider": "privy", "policyConfigured": bool(os.getenv("PRIVY_POLICY_ID")), "autonomousTradeLimitUsd": float(os.getenv("FUND_MAX_TRADE_USD", "10"))}, "executionBoundary": "proposal-only" if self.execution.mode.value == "dry-run" else "guarded"}
    def portfolio_update(self) -> dict[str, Any]: return {"fund": {**self.status(), **self.portfolio.snapshot().as_dict()}, "demoData": False}
    def trade_history(self) -> dict[str, Any]: return {"trades": self.ledger.rows("trades", limit=50), "demoData": False}

