"""Autonomous fly allocation, netting, accounting, and execution adapters."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

from malecns.swarm.observer import BehaviorTradeIntent

from ..market.uniswap_client import UniswapTradingClient
from .ledger import FundLedger
from .wallet import ZERO_ADDRESS, RpcWalletClient, WalletRpcError


ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class FlyBehaviorState(str, Enum):
    EXPLORING = "EXPLORING"
    APPROACHING = "APPROACHING"
    QUALIFYING = "QUALIFYING"
    HOLDING = "HOLDING"
    DEPARTING = "DEPARTING"


@dataclass(frozen=True)
class TokenRef:
    chain_id: int
    address: str
    symbol: str
    liquidity_usd: float | None = None
    price_usd: float | None = None
    price_native: float | None = None

    @classmethod
    def from_habitat(cls, habitat: Mapping[str, Any]) -> "TokenRef | None":
        address = str(habitat.get("tokenAddress") or "").strip()
        if not ADDRESS_RE.fullmatch(address):
            return None
        chain = str(habitat.get("chainId") or "robinhood").lower()
        chain_id = int(os.getenv("FUND_CHAIN_ID", "4663")) if chain == "robinhood" else int(chain)
        values: dict[str, Any] = {}
        for signal in habitat.get("signals") or ():
            if isinstance(signal, Mapping) and signal.get("name"):
                values[str(signal["name"])] = signal.get("value")
        return cls(
            chain_id,
            address,
            str(habitat.get("label") or address[:8]),
            _number(values.get("liquidity.usd")),
            _number(values.get("market.priceUsd")),
            _number(values.get("market.priceNative")),
        )


@dataclass(frozen=True)
class FlyCapitalPosition:
    fly_id: str
    state: str = FlyBehaviorState.EXPLORING.value
    chain_id: int | None = None
    token_address: str | None = None
    token_symbol: str | None = None
    allocation_fraction: float = 0.0625
    entry_timestamp_ms: int | None = None
    entry_price_usd: float | None = None
    held_amount: float = 0.0
    current_value_usd: float = 0.0
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    departure_reason: str | None = None
    updated_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "flyId": self.fly_id,
            "state": self.state,
            "chainId": self.chain_id,
            "tokenAddress": self.token_address,
            "tokenSymbol": self.token_symbol,
            "allocationFraction": self.allocation_fraction,
            "allocationPercent": self.allocation_fraction * 100.0,
            "entryTimestampMs": self.entry_timestamp_ms,
            "entryPriceUsd": self.entry_price_usd,
            "heldAmount": self.held_amount,
            "currentValueUsd": self.current_value_usd,
            "realizedPnlUsd": self.realized_pnl_usd,
            "unrealizedPnlUsd": self.unrealized_pnl_usd,
            "departureReason": self.departure_reason,
            "updatedMs": self.updated_ms,
        }

    def ledger_dict(self) -> dict[str, Any]:
        return {
            "fly_id": self.fly_id,
            "state": self.state,
            "chain_id": self.chain_id,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "allocation_fraction": self.allocation_fraction,
            "entry_timestamp_ms": self.entry_timestamp_ms,
            "entry_price_usd": self.entry_price_usd,
            "held_amount": self.held_amount,
            "current_value_usd": self.current_value_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "unrealized_pnl_usd": self.unrealized_pnl_usd,
            "departure_reason": self.departure_reason,
            "updated_ms": self.updated_ms,
        }


@dataclass(frozen=True)
class AllocationIntent:
    """The biology-owned allocation decision for one primary CNS fly."""

    fly_id: str
    side: str
    token: TokenRef
    allocation_fraction: float
    reason: str
    observed_at_ms: int


@dataclass(frozen=True)
class PortfolioDelta:
    """A netted portfolio change produced after allocation decisions."""

    side: str
    token: TokenRef
    fly_ids: tuple[str, ...]
    amount_in: int
    token_in: str
    token_out: str
    reason: str


@dataclass(frozen=True)
class MarketRiskGuard:
    """Market/execution checks kept independent from fly behavior."""

    min_liquidity_usd: float = 0.0

    def reject_reason(self, token: TokenRef) -> str | None:
        if token.liquidity_usd is None or token.liquidity_usd < self.min_liquidity_usd:
            return "minimum liquidity"
        return None


@dataclass(frozen=True)
class ExecutionIntent:
    idempotency_key: str
    side: str
    chain_id: int
    token_in: str
    token_out: str
    amount_in: str
    fly_ids: tuple[str, ...]
    slippage_tolerance: float
    created_at_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "idempotencyKey": self.idempotency_key,
            "side": self.side,
            "chainId": self.chain_id,
            "tokenIn": self.token_in,
            "tokenOut": self.token_out,
            "amountIn": self.amount_in,
            "flyIds": list(self.fly_ids),
            "slippageTolerance": self.slippage_tolerance,
            "createdAtMs": self.created_at_ms,
        }


class ExecutionAdapter(Protocol):
    def execute(self, intent: ExecutionIntent, token: TokenRef) -> Mapping[str, Any]: ...


class SimulationExecutionAdapter:
    """Fully automatic deterministic adapter for tests and the demo."""

    def execute(self, intent: ExecutionIntent, token: TokenRef) -> Mapping[str, Any]:
        amount = float(intent.amount_in)
        output = amount / max(token.price_native or 1.0, 1e-18)
        digest = hashlib.sha256(intent.idempotency_key.encode()).hexdigest()[:24]
        return {"status": "filled", "txHash": f"0xsim{digest}", "amountOut": str(output), "gas": "0", "slippage": 0.0, "executionPrice": token.price_native}


class MainnetExecutionAdapter:
    """Uniswap quote/transaction preparation adapter.

    It validates the external transaction boundary and returns a ready-to-sign
    transaction. Broadcasting remains owned by the platform authorization
    boundary and is intentionally not performed here.
    """

    def __init__(self, wallet: RpcWalletClient, client: UniswapTradingClient) -> None:
        self.wallet = wallet
        self.client = client

    def execute(self, intent: ExecutionIntent, token: TokenRef) -> Mapping[str, Any]:
        wallet = self.wallet.snapshot()
        if wallet.chain_id != intent.chain_id:
            raise WalletRpcError("execution chain does not match wallet RPC chain")
        if intent.token_in.lower() == ZERO_ADDRESS.lower() and int(intent.amount_in) > wallet.available_native_wei:
            raise WalletRpcError("insufficient native balance after gas reserve")
        if intent.token_in.lower() != ZERO_ADDRESS.lower():
            approval = self.client.check_approval({"walletAddress": wallet.wallet_address, "token": intent.token_in, "amount": intent.amount_in, "chainId": intent.chain_id, "tokenOut": intent.token_out, "tokenOutChainId": intent.chain_id})
            if approval.get("approval"):
                return {"status": "approval_required", "approval": approval, "txHash": None}
        quote = self.client.quote({"swapper": wallet.wallet_address, "tokenIn": intent.token_in, "tokenOut": intent.token_out, "tokenInChainId": str(intent.chain_id), "tokenOutChainId": str(intent.chain_id), "amount": intent.amount_in, "type": "EXACT_INPUT", "slippageTolerance": intent.slippage_tolerance})
        swap = self.client.create_unsigned_swap(quote)
        tx = swap.get("swap")
        if not isinstance(tx, Mapping) or not isinstance(tx.get("to"), str) or not ADDRESS_RE.fullmatch(str(tx.get("to"))) or not isinstance(tx.get("data"), str) or tx.get("data") in {"", "0x"} or tx.get("value") is None:
            raise WalletRpcError("Uniswap returned an invalid transaction payload")
        try:
            estimated_gas = self.wallet.call("eth_estimateGas", [{"from": wallet.wallet_address, "to": tx["to"], "data": tx["data"], "value": str(tx["value"])}, "latest"])
        except Exception as exc:
            raise WalletRpcError(f"gas estimation failed: {exc}") from exc
        nonce = self.wallet.call("eth_getTransactionCount", [wallet.wallet_address, "pending"])
        return {"status": "prepared_external_authorization", "txHash": None, "quote": quote, "swap": swap, "nonce": nonce, "estimatedGas": estimated_gas, "executionPrice": token.price_native, "gas": quote.get("gasFee") or quote.get("gasFeeUSD"), "slippage": intent.slippage_tolerance}


class AutonomousTradingRuntime:
    """Stateful 16-fly allocation runtime with netted execution intents."""

    def __init__(self, ledger: FundLedger, *, expected_agents: int = 16, wallet: RpcWalletClient | None = None, adapter: ExecutionAdapter | None = None, departure_debounce_ms: int = 1_500, min_liquidity_usd: float = 0.0, slippage_tolerance: float = 0.5) -> None:
        self.ledger = ledger
        self.expected_agents = max(1, int(expected_agents))
        self.wallet = wallet
        self.adapter = adapter or SimulationExecutionAdapter()
        self.departure_debounce_ms = max(0, int(departure_debounce_ms))
        self.min_liquidity_usd = max(0.0, float(min_liquidity_usd))
        self.risk_guard = MarketRiskGuard(self.min_liquidity_usd)
        # Keep an intentionally tight upper bound even if an env value is
        # mistyped; this is a market guard, not a biological preference.
        self.slippage_tolerance = min(5.0, max(0.0, float(slippage_tolerance)))
        self.tokens: dict[str, TokenRef] = {}
        self.tokens_by_address: dict[str, TokenRef] = {}
        self.positions: dict[str, FlyCapitalPosition] = {}
        self.pending_departures: dict[str, tuple[int, str, TokenRef]] = {}
        self.processed_events = {str(row["idempotency_key"]) for row in self.ledger.rows("execution_attempts", limit=100000)}
        for index in range(1, self.expected_agents + 1):
            fly_id = f"fly-{index:03d}"
            self.positions[fly_id] = FlyCapitalPosition(fly_id, allocation_fraction=1.0 / self.expected_agents)
        for row in self.ledger.rows("fly_positions", limit=100000):
            self.positions[str(row["fly_id"])] = FlyCapitalPosition(str(row["fly_id"]), str(row["state"]), row["chain_id"], row["token_address"], row["token_symbol"], float(row["allocation_fraction"]), row["entry_timestamp_ms"], row["entry_price_usd"], float(row.get("held_amount") or 0), float(row["current_value_usd"]), float(row["realized_pnl_usd"]), float(row["unrealized_pnl_usd"]), row["departure_reason"], int(row["updated_ms"]))
        self.events: list[dict[str, Any]] = []
        self.pending_rebalance: list[dict[str, Any]] = []

    @classmethod
    def from_env(cls, ledger: FundLedger, wallet: RpcWalletClient | None = None) -> "AutonomousTradingRuntime":
        client = UniswapTradingClient.from_env()
        mode = os.getenv("FUND_ADAPTER", "simulation").lower()
        adapter: ExecutionAdapter = SimulationExecutionAdapter()
        if mode == "mainnet" and wallet is not None and client is not None:
            adapter = MainnetExecutionAdapter(wallet, client)
        return cls(ledger, expected_agents=16, wallet=wallet, adapter=adapter, departure_debounce_ms=int(os.getenv("FUND_DEPARTURE_DEBOUNCE_MS", "1500")), min_liquidity_usd=float(os.getenv("FUND_MIN_LIQUIDITY_USD", "0")), slippage_tolerance=float(os.getenv("FUND_SLIPPAGE_TOLERANCE", "0.5")))

    def update_habitats(self, habitats: Iterable[Mapping[str, Any]]) -> None:
        for habitat in habitats:
            token = TokenRef.from_habitat(habitat)
            if token is not None:
                self.tokens[str(habitat.get("id"))] = token
                self.tokens_by_address[_token_key(token.chain_id, token.address)] = token
                for fly_id, position in self.positions.items():
                    if position.token_address and position.token_address.lower() == token.address.lower() and position.state == FlyBehaviorState.HOLDING.value:
                        current = (token.price_usd or 0.0) * position.held_amount
                        basis = (position.entry_price_usd or 0.0) * position.held_amount
                        self._save(replace(position, current_value_usd=current, unrealized_pnl_usd=current - basis, updated_ms=int(time.time() * 1000)))

    def ingest(self, intents: Iterable[BehaviorTradeIntent], *, observed_at_ms: int | None = None) -> dict[str, Any]:
        timestamp = int(observed_at_ms or time.time() * 1000)
        actions: list[AllocationIntent] = []
        self._flush_departures(timestamp, actions)
        for behavior in intents:
            if behavior.intent_id in self.processed_events:
                continue
            token = self.tokens.get(behavior.habitat_id)
            if token is None:
                self._event(behavior, "BLOCKED", "token identity unavailable")
                self.processed_events.add(behavior.intent_id)
                continue
            position = self.positions.setdefault(behavior.fly_id, FlyCapitalPosition(behavior.fly_id, allocation_fraction=1.0 / self.expected_agents))
            if behavior.side == "buy":
                if position.token_address and position.token_address.lower() == token.address.lower() and position.state in {FlyBehaviorState.HOLDING.value, FlyBehaviorState.QUALIFYING.value}:
                    self._save(replace(position, state=FlyBehaviorState.HOLDING.value, updated_ms=timestamp))
                    self._event(behavior, "HOLD", "continued commitment")
                else:
                    if position.token_address and position.held_amount > 0:
                        old = self.tokens_by_address.get(_token_key(position.chain_id or token.chain_id, position.token_address)) or TokenRef(position.chain_id or token.chain_id, position.token_address, position.token_symbol or position.token_address[:8])
                        actions.append(AllocationIntent(behavior.fly_id, "sell", old, position.allocation_fraction, "rotation", timestamp))
                    self._save(replace(position, state=FlyBehaviorState.QUALIFYING.value, updated_ms=timestamp))
                    actions.append(AllocationIntent(behavior.fly_id, "buy", token, position.allocation_fraction, behavior.reason, timestamp))
                self.processed_events.add(behavior.intent_id)
            elif behavior.side == "sell" and position.token_address and position.token_address.lower() == token.address.lower() and position.held_amount > 0:
                self.pending_departures[behavior.fly_id] = (timestamp + self.departure_debounce_ms, behavior.reason, token)
                self._save(replace(position, state=FlyBehaviorState.DEPARTING.value, departure_reason=behavior.reason, updated_ms=timestamp))
                self._event(behavior, "DEPARTING", "debounce started")
                self.processed_events.add(behavior.intent_id)
        self._execute_netted(actions, timestamp)
        return self.snapshot(timestamp)

    def snapshot(self, observed_at_ms: int | None = None) -> dict[str, Any]:
        timestamp = int(observed_at_ms or time.time() * 1000)
        wallet: dict[str, Any] = {"configured": self.wallet is not None}
        if self.wallet is not None:
            try:
                wallet = {"configured": True, **self.wallet.snapshot().as_dict()}
            except Exception as exc:
                wallet = {"configured": True, "status": "error", "error": str(exc)}
        deployable = int(wallet.get("availableToTradeWei") or 0)
        biological: dict[tuple[int, str], float] = {}
        for position in self.positions.values():
            if position.state == FlyBehaviorState.HOLDING.value and position.token_address:
                identity = (position.chain_id or 0, position.token_address)
                biological[identity] = biological.get(identity, 0.0) + position.allocation_fraction
        actual_by_token: dict[str, dict[str, Any]] = {}
        for position in self.positions.values():
            if position.state != FlyBehaviorState.HOLDING.value or not position.token_address:
                continue
            key = f"{position.chain_id}:{position.token_address.lower()}"
            item = actual_by_token.setdefault(key, {"chainId": position.chain_id, "tokenAddress": position.token_address, "tokenSymbol": position.token_symbol, "intendedAmount": 0.0, "intendedValueUsd": 0.0, "flyIds": []})
            item["intendedAmount"] += position.held_amount
            item["intendedValueUsd"] += position.current_value_usd
            item["flyIds"].append(position.fly_id)
        actual = []
        if self.wallet is not None and wallet.get("nativeBalance") is not None:
            actual.append({
                "chainId": wallet.get("chainId"),
                "tokenAddress": ZERO_ADDRESS,
                "tokenSymbol": wallet.get("nativeSymbol", "ETH"),
                "intendedAmount": 0.0,
                "intendedValueUsd": 0.0,
                "observedAmount": wallet.get("nativeBalance"),
                "observedBalanceWei": wallet.get("nativeBalanceWei"),
                "gasReserve": wallet.get("gasReserve"),
                "reconciliation": "reserve-separated",
                "flyIds": [],
            })
        for item in actual_by_token.values():
            if self.wallet is not None:
                try:
                    decimals = self.wallet.erc20_decimals(item["tokenAddress"])
                    raw = self.wallet.erc20_balance_raw(item["tokenAddress"])
                    observed_amount = raw / (10**decimals)
                    item.update({"observedBalanceRaw": str(raw), "observedDecimals": decimals, "observedAmount": observed_amount, "amountDelta": observed_amount - item["intendedAmount"], "reconciliation": "matched" if abs(observed_amount - item["intendedAmount"]) <= 1e-12 else "discrepancy"})
                except Exception as exc:
                    item["observationError"] = str(exc)
            actual.append(item)
        return {
            "observedAtMs": timestamp,
            "flyCount": self.expected_agents,
            "executionAdapter": type(self.adapter).__name__,
            "executionBoundary": "simulation-fill" if isinstance(self.adapter, SimulationExecutionAdapter) else "transaction-preparation-only",
            "externalBroadcast": False,
            "perFlyAllocationFraction": 1.0 / self.expected_agents,
            "perFlyAllocationPercent": 100.0 / self.expected_agents,
            "perFlyBudgetWei": str(deployable // self.expected_agents),
            "wallet": wallet,
            "flies": [self.positions[f"fly-{index:03d}"].as_dict() for index in range(1, self.expected_agents + 1)],
            "biologicalTargetPortfolio": [{"chainId": chain_id, "tokenAddress": token, "allocationFraction": fraction, "allocationPercent": fraction * 100.0} for (chain_id, token), fraction in biological.items()],
            "actualWalletPortfolio": actual,
            "pendingRebalance": list(self.pending_rebalance[-100:]),
            "events": list(self.events[-100:]),
        }

    def _flush_departures(self, timestamp: int, actions: list[AllocationIntent]) -> None:
        for fly_id, (due, reason, token) in list(self.pending_departures.items()):
            if timestamp < due:
                continue
            position = self.positions[fly_id]
            if position.state == FlyBehaviorState.DEPARTING.value and position.held_amount > 0:
                actions.append(AllocationIntent(fly_id, "sell", token, position.allocation_fraction, reason, timestamp))
            self.pending_departures.pop(fly_id, None)

    def _execute_netted(self, actions: list[AllocationIntent], timestamp: int) -> None:
        grouped: dict[tuple[str, int, str], list[tuple[str, TokenRef, str]]] = {}
        for action in actions:
            side, fly_id, token, reason = action.side, action.fly_id, action.token, action.reason
            if (risk_reason := self.risk_guard.reject_reason(token)) is not None:
                self.pending_rebalance.append({"status": "blocked", "reason": risk_reason, "flyId": fly_id, "tokenAddress": token.address})
                continue
            grouped.setdefault((side, token.chain_id, token.address.lower()), []).append((fly_id, token, reason))
        for (side, chain_id, token_address), group in grouped.items():
            fly_ids = tuple(item[0] for item in group)
            token = group[0][1]
            if side == "buy":
                amount = self._buy_amount_wei(len(group))
                token_in, token_out = ZERO_ADDRESS, token.address
            else:
                amount = sum(self.positions[fly_id].held_amount for fly_id in fly_ids)
                token_in, token_out = token.address, ZERO_ADDRESS
            if amount <= 0:
                self.pending_rebalance.append({"status": "blocked", "reason": "insufficient balance or allocation", "side": side, "flyIds": list(fly_ids), "tokenAddress": token.address})
                continue
            if side == "sell":
                amount = int(amount)
                if amount <= 0:
                    self.pending_rebalance.append({"status": "blocked", "reason": "sell amount below token base unit", "side": side, "flyIds": list(fly_ids), "tokenAddress": token.address})
                    continue
            reason = ",".join(sorted({item[2] for item in group}))
            delta = PortfolioDelta(side, token, fly_ids, amount, token_in, token_out, reason)
            key = f"{delta.side}:{chain_id}:{token_address}:{','.join(fly_ids)}:{timestamp}"
            intent = ExecutionIntent(hashlib.sha256(key.encode()).hexdigest(), delta.side, chain_id, delta.token_in, delta.token_out, str(delta.amount_in), delta.fly_ids, self.slippage_tolerance, timestamp)
            if intent.idempotency_key in self.processed_events:
                continue
            attempt = {"attempt_id": intent.idempotency_key, "idempotency_key": intent.idempotency_key, "status": "pending", "side": side, "chain_id": chain_id, "token_in": token_in, "token_out": token_out, "amount_in": str(amount), "amount_out": None, "fly_ids_json": json.dumps(list(fly_ids)), "execution_price": None, "gas": None, "slippage": self.slippage_tolerance, "tx_hash": None, "nonce": None, "error": None, "created_ms": timestamp, "updated_ms": timestamp}
            status = "blocked"
            amount_out = 0.0
            try:
                result = self.adapter.execute(intent, token)
                status = str(result.get("status", "prepared"))
                amount_out = float(result.get("amountOut") or 0)
                attempt.update({"status": status, "amount_out": str(amount_out), "execution_price": result.get("executionPrice"), "gas": result.get("gas"), "tx_hash": result.get("txHash"), "nonce": result.get("nonce"), "updated_ms": int(time.time() * 1000)})
                if status in {"filled", "simulated"}:
                    self._apply_fill(side, group, amount_out, token, timestamp)
                else:
                    self.pending_rebalance.append({"status": status, "side": side, "flyIds": list(fly_ids), "tokenAddress": token.address, "amountIn": str(amount), "nonce": result.get("nonce"), "approval": result.get("approval"), "quote": result.get("quote"), "preparedTransaction": result.get("swap"), "executionIntent": intent.as_dict()})
                self.events.append({"type": side.upper(), "status": status, "flyIds": list(fly_ids), "tokenAddress": token.address, "amountIn": str(amount), "amountOut": str(amount_out), "executionPrice": result.get("executionPrice"), "gas": result.get("gas"), "estimatedGas": result.get("estimatedGas"), "slippage": result.get("slippage", self.slippage_tolerance), "nonce": result.get("nonce"), "txHash": result.get("txHash")})
            except Exception as exc:
                attempt.update({"status": "blocked", "error": str(exc), "updated_ms": int(time.time() * 1000)})
                self.pending_rebalance.append({"status": "blocked", "reason": str(exc), "side": side, "flyIds": list(fly_ids), "tokenAddress": token.address})
            self.ledger.record_trade({"trade_id": intent.idempotency_key, "timestamp_ms": timestamp, "chain_id": chain_id, "dex_id": "uniswap", "token_in": token_in, "token_out": token_out, "amount_in": str(amount), "amount_out": str(amount_out), "usd_value": (token.price_usd or 0.0) * amount_out, "tx_hash": attempt.get("tx_hash"), "status": status, "neuroswarm_decision_id": ",".join(fly_ids), "fees_usd": None, "gas_usd": None})
            self.ledger.record_execution_attempt(attempt)
            self.processed_events.add(intent.idempotency_key)

    def _apply_fill(self, side: str, group: list[tuple[str, TokenRef, str]], amount_out: float, token: TokenRef, timestamp: int) -> None:
        if side == "buy":
            per_fly = amount_out / max(1, len(group))
            for fly_id, _, _ in group:
                position = self.positions[fly_id]
                self._save(replace(position, state=FlyBehaviorState.HOLDING.value, chain_id=token.chain_id, token_address=token.address, token_symbol=token.symbol, entry_timestamp_ms=timestamp, entry_price_usd=token.price_usd, held_amount=per_fly, current_value_usd=(token.price_usd or 0.0) * per_fly, unrealized_pnl_usd=0.0, departure_reason=None, updated_ms=timestamp))
        else:
            for fly_id, _, reason in group:
                position = self.positions[fly_id]
                current = (token.price_usd or position.entry_price_usd or 0.0) * position.held_amount
                basis = (position.entry_price_usd or 0.0) * position.held_amount
                self._save(replace(position, state=FlyBehaviorState.EXPLORING.value, token_address=None, token_symbol=None, held_amount=0.0, current_value_usd=0.0, realized_pnl_usd=position.realized_pnl_usd + current - basis, unrealized_pnl_usd=0.0, departure_reason=reason, updated_ms=timestamp))

    def _buy_amount_wei(self, count: int) -> int:
        if self.wallet is None:
            return 10**15 * count
        try:
            return (self.wallet.snapshot().available_native_wei // self.expected_agents) * count
        except Exception:
            return 0

    def _save(self, position: FlyCapitalPosition) -> None:
        self.positions[position.fly_id] = position
        self.ledger.upsert_fly_position(position.ledger_dict())

    def _event(self, behavior: BehaviorTradeIntent, event_type: str, reason: str) -> None:
        self.events.append({"type": event_type, "status": "observed", "flyId": behavior.fly_id, "habitatId": behavior.habitat_id, "side": behavior.side, "reason": reason, "observedAtMs": behavior.observed_at_ms, "confidence": behavior.confidence})


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _token_key(chain_id: int, address: str) -> str:
    """Resolve assets by network and contract, never by symbol alone."""
    return f"{int(chain_id)}:{address.lower()}"
