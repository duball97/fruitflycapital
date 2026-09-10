"""Execution boundary with hard defaults against accidental live trading."""
from __future__ import annotations
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol
from .models import TradeIntent

class FundExecutionMode(str, Enum): DRY_RUN = "dry-run"; TESTNET = "testnet"; LIVE = "live"
@dataclass(frozen=True)
class ExecutionRecord:
    status: str; mode: str; trade_intent: Mapping[str, Any]; reason: str
    def as_dict(self) -> dict[str, Any]: return {"status": self.status, "mode": self.mode, "tradeIntent": dict(self.trade_intent), "reason": self.reason}
class ExecutionAdapter(Protocol):
    def execute(self, intent: TradeIntent) -> Mapping[str, Any]: ...
class FakeExecutionAdapter:
    def __init__(self) -> None: self.calls: list[TradeIntent] = []
    def execute(self, intent: TradeIntent) -> Mapping[str, Any]: self.calls.append(intent); return {"status": "simulated", "txHash": None}
class ExecutionEngine:
    def __init__(self, mode: FundExecutionMode | str | None = None, *, adapter: ExecutionAdapter | None = None, live_confirmed: bool | None = None) -> None:
        self.mode = FundExecutionMode(mode or os.getenv("FUND_EXECUTION_MODE", "dry-run")); self.adapter = adapter; self.live_confirmed = bool(live_confirmed if live_confirmed is not None else os.getenv("FUND_LIVE_TRADING_CONFIRMED", "false").lower() == "true")
    def execute(self, intent: TradeIntent, *, explicit_confirmation: bool = False) -> ExecutionRecord:
        if self.mode == FundExecutionMode.DRY_RUN: return ExecutionRecord("proposal_only", self.mode.value, intent.as_dict(), "dry-run never signs or broadcasts")
        if self.mode == FundExecutionMode.LIVE and not (self.live_confirmed and explicit_confirmation): return ExecutionRecord("blocked", self.mode.value, intent.as_dict(), "live mode requires environment confirmation and explicit confirmation")
        if self.adapter is None: return ExecutionRecord("blocked", self.mode.value, intent.as_dict(), "no execution adapter configured")
        result = self.adapter.execute(intent); return ExecutionRecord(str(result.get("status", "submitted")), self.mode.value, intent.as_dict(), "adapter result; inspect tx status separately")
