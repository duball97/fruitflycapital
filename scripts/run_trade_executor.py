#!/usr/bin/env python3
"""Run the separate FruitFly execution service.

The brain server publishes netted ExecutionIntent records when
``FUND_ADAPTER=queue``. This process consumes those records, discovers a
direct on-chain Uniswap V2/V3 route over JSON-RPC, handles approval
transactions when needed, and can either prepare or broadcast the transaction.

Examples:
    PYTHONPATH=src .venv/bin/python scripts/run_trade_executor.py --once
    FUND_RUNNER_CONFIRM_BROADCAST=true \
      PYTHONPATH=src .venv/bin/python scripts/run_trade_executor.py --mode broadcast
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from malecns.config import load_project_env
from malecns.fund.autonomous import AutonomousTradingRuntime, ExecutionIntent, TokenRef
from malecns.fund.ledger import FundLedger
from malecns.fund.wallet import ZERO_ADDRESS, RpcWalletClient, WalletRpcError
from malecns.market.direct_uniswap import DirectUniswapClient
from malecns.market.uniswap_client import UniswapApiError, UniswapTradingClient
from malecns.fund.supabase_queue import SupabaseIntentQueue


ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
AMOUNT_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def _int_value(value: Any) -> int:
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def _address(value: Any, field: str) -> str:
    text = str(value or "")
    if not ADDRESS_RE.fullmatch(text):
        raise ValueError(f"{field} must be a 20-byte 0x-prefixed address")
    return text


def _amount(value: Any, field: str) -> str:
    text = str(value or "")
    if not AMOUNT_RE.fullmatch(text):
        raise ValueError(f"{field} must be a non-negative decimal amount")
    return text


def _rpc_transaction(transaction: Mapping[str, Any], wallet_address: str) -> dict[str, Any]:
    result = dict(transaction)
    result["from"] = wallet_address
    for key in ("value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas", "nonce", "chainId"):
        if key in result and result[key] is not None:
            result[key] = hex(_int_value(result[key]))
    return result


def _transaction_from_swap(payload: Mapping[str, Any]) -> dict[str, Any]:
    candidate = payload.get("swap") or payload.get("transaction")
    if not isinstance(candidate, Mapping):
        candidate = payload
    to = candidate.get("to")
    data = candidate.get("data") or candidate.get("calldata")
    if not isinstance(to, str) or not ADDRESS_RE.fullmatch(to):
        raise ValueError("swap response did not include a valid transaction recipient")
    if not isinstance(data, str) or not data.startswith("0x") or len(data) < 4:
        raise ValueError("swap response did not include valid calldata")
    transaction: dict[str, Any] = {"to": to, "data": data, "value": _int_value(candidate.get("value", 0))}
    for key in ("gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas", "nonce", "chainId"):
        if candidate.get(key) is not None:
            transaction[key] = _int_value(candidate[key])
    if candidate.get("gasLimit") is not None and candidate.get("gas") is None:
        transaction["gas"] = _int_value(candidate["gasLimit"])
    return transaction


def _load_record(raw: str) -> tuple[ExecutionIntent, TokenRef]:
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise ValueError("queue item must be a JSON object")
    raw_intent = payload.get("executionIntent")
    raw_token = payload.get("token")
    if not isinstance(raw_intent, Mapping) or not isinstance(raw_token, Mapping):
        raise ValueError("queue item must contain executionIntent and token")
    chain_id = int(raw_intent.get("chainId"))
    token_in = _address(raw_intent.get("tokenIn"), "tokenIn")
    token_out = _address(raw_intent.get("tokenOut"), "tokenOut")
    amount_in = _amount(raw_intent.get("amountIn"), "amountIn")
    token_address = _address(raw_token.get("address"), "token.address")
    if chain_id != int(raw_token.get("chainId")):
        raise ValueError("intent and token chain IDs do not match")
    intent = ExecutionIntent(
        idempotency_key=str(raw_intent.get("idempotencyKey") or ""),
        side=str(raw_intent.get("side") or "").lower(),
        chain_id=chain_id,
        token_in=token_in,
        token_out=token_out,
        amount_in=amount_in,
        fly_ids=tuple(str(item) for item in (raw_intent.get("flyIds") or [])),
        slippage_tolerance=float(raw_intent.get("slippageTolerance") or 0.5),
        created_at_ms=int(raw_intent.get("createdAtMs") or time.time() * 1000),
        biological_event_id=str(raw_intent.get("biologicalEventId") or "") or None,
    )
    if not intent.idempotency_key or intent.side not in {"buy", "sell"}:
        raise ValueError("intent requires an idempotency key and BUY/SELL side")
    token = TokenRef(
        chain_id=chain_id,
        address=token_address,
        symbol=str(raw_token.get("symbol") or token_address[:8]),
        liquidity_usd=float(raw_token["liquidityUsd"]) if raw_token.get("liquidityUsd") is not None else None,
        price_usd=float(raw_token["priceUsd"]) if raw_token.get("priceUsd") is not None else None,
        price_native=float(raw_token["priceNative"]) if raw_token.get("priceNative") is not None else None,
    )
    if intent.side == "buy" and intent.token_out.lower() != token.address.lower():
        raise ValueError("BUY tokenOut does not match token identity")
    if intent.side == "sell" and intent.token_in.lower() != token.address.lower():
        raise ValueError("SELL tokenIn does not match token identity")
    return intent, token


def _brain_health_url() -> str:
    """Resolve the HTTP health URL paired with the brain WebSocket."""

    value = os.getenv("FUND_BRAIN_HEALTH_URL", "").strip() or os.getenv("VITE_BRAIN_WS_URL", "").strip()
    if value.startswith("ws://"):
        value = "http://" + value[5:]
    elif value.startswith("wss://"):
        value = "https://" + value[6:]
    if value and not re.search(r"/healthz(?:\?|$)", value):
        value = value.rstrip("/") + "/healthz"
    return value


def _brain_is_healthy(url: str) -> bool:
    if not url:
        return True
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status != 200:
                return False
            raw = response.read().decode("utf-8", errors="replace")
            if not raw:
                return True
            payload = json.loads(raw)
            return not isinstance(payload, Mapping) or payload.get("status") in {None, "ok"}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False


class TradeExecutor:
    def __init__(self, mode: str, shared_queue: SupabaseIntentQueue | None = None) -> None:
        self.mode = mode
        self.shared_queue = shared_queue
        self.wallet = RpcWalletClient.from_env()
        if self.wallet is None:
            raise RuntimeError("FUND_RPC_URL and FUND_WALLET_ADDRESS are required")
        self.api_client = UniswapTradingClient.from_env()
        # Keep the direct RPC route available even when a hosted API key is
        # configured.  The hosted endpoint can be blocked by Cloudflare
        # (HTTP 403), while the on-chain V2/V3 route remains usable.
        self.direct_client = DirectUniswapClient.from_env(self.wallet)
        self.client = self.api_client or self.direct_client
        if mode == "broadcast" and os.getenv("FUND_RUNNER_CONFIRM_BROADCAST", "false").lower() != "true":
            raise RuntimeError("set FUND_RUNNER_CONFIRM_BROADCAST=true to enable broadcasting")
        # In Supabase queue mode the brain service owns the canonical queue.
        # Do not open its SQLite file from the worker: on a local machine that
        # causes lock contention, and on Render the two services cannot share
        # that filesystem anyway. The worker ledger is only an execution-side
        # idempotency/receipt cache; queue state lives in Supabase.
        ledger_path = os.getenv("FUND_RUNNER_DB_PATH")
        if not ledger_path and os.getenv("FUND_INTENT_QUEUE_BACKEND", "").lower() == "supabase":
            ledger_path = "data/fund/executor.db"
        ledger = FundLedger(ledger_path or os.getenv("FUND_DB_PATH", "data/fund/fund.db"))
        self.runtime = AutonomousTradingRuntime.from_env(ledger, self.wallet)

    def emergency_sell_confirmed_holdings(
        self,
        queue: SupabaseIntentQueue,
        *,
        incident_id: str,
    ) -> list[dict[str, Any]]:
        """Queue full-balance SELLs for confirmed BUY holdings.

        This is a recovery mechanism for a brain-service outage. It only
        creates durable Supabase SELL intents; the normal executor loop still
        performs all quote, approval, gas, signer, and broadcast checks.
        Holdings are discovered from the wallet RPC, so a stale local ledger
        cannot cause an incorrect sell amount.
        """

        holdings: dict[tuple[int, str], dict[str, Any]] = {}
        for row in queue.execution_results(limit=500):
            if str(row.get("side") or "").lower() != "buy":
                continue
            if str(row.get("status") or "").lower() != "confirmed":
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
            raw_token = payload.get("token") if isinstance(payload.get("token"), Mapping) else {}
            token_address = str(
                raw_token.get("address")
                or row.get("token_out")
                or ""
            )
            if not ADDRESS_RE.fullmatch(token_address) or token_address.lower() == ZERO_ADDRESS.lower():
                continue
            chain_id = int(row.get("chain_id") or raw_token.get("chainId") or self.wallet.expected_chain_id or 4663)
            key = (chain_id, token_address.lower())
            item = holdings.setdefault(
                key,
                {
                    "chainId": chain_id,
                    "address": token_address,
                    "symbol": str(raw_token.get("symbol") or token_address[:8]),
                    "liquidityUsd": raw_token.get("liquidityUsd"),
                    "priceUsd": raw_token.get("priceUsd"),
                    "priceNative": raw_token.get("priceNative"),
                    "flyIds": set(),
                },
            )
            item["flyIds"].update(str(fly_id) for fly_id in (row.get("fly_ids") or []) if str(fly_id))

        queued: list[dict[str, Any]] = []
        for item in holdings.values():
            token_address = str(item["address"])
            try:
                balance_raw = self.wallet.erc20_balance_raw(token_address)
            except Exception as exc:
                queued.append({"status": "skipped", "tokenAddress": token_address, "reason": f"balance read failed: {exc}"})
                continue
            if balance_raw <= 0:
                continue
            digest = hashlib.sha256(f"{incident_id}:{item['chainId']}:{token_address.lower()}".encode()).hexdigest()
            execution_id = f"server-down-sell:{digest}"
            intent = ExecutionIntent(
                idempotency_key=execution_id,
                side="sell",
                chain_id=int(item["chainId"]),
                token_in=token_address,
                token_out=ZERO_ADDRESS,
                amount_in=str(balance_raw),
                fly_ids=tuple(sorted(item["flyIds"])),
                slippage_tolerance=float(os.getenv("FUND_SLIPPAGE_TOLERANCE", "0.5")),
                created_at_ms=int(time.time() * 1000),
                biological_event_id=f"server-down:{incident_id}:{item['chainId']}:{token_address.lower()}",
            )
            payload = {
                "executionIntent": intent.as_dict(),
                "token": {
                    "chainId": int(item["chainId"]),
                    "address": token_address,
                    "symbol": item["symbol"],
                    "liquidityUsd": item["liquidityUsd"],
                    "priceUsd": item["priceUsd"],
                    "priceNative": item["priceNative"],
                },
                "queuedAtMs": int(time.time() * 1000),
                "emergencyReason": "brain server health endpoint stale",
            }
            queue.enqueue(payload)
            queued.append({"status": "queued", "side": "sell", "token": item["symbol"], "tokenAddress": token_address, "amountRaw": str(balance_raw), "executionId": execution_id})
        return queued

    def process(self, intent: ExecutionIntent, token: TokenRef) -> dict[str, Any]:
        # A process crash after broadcast but before the queue offset is
        # flushed must not submit the same biological intent twice.
        existing = next(
            (row for row in self.runtime.ledger.rows("mainnet_executions", limit=100000)
             if str(row.get("execution_id")) == intent.idempotency_key),
            None,
        )
        if existing is not None and existing.get("tx_hash"):
            return {
                "status": "already_recorded",
                "executionId": intent.idempotency_key,
                "txHash": existing["tx_hash"],
                "receiptStatus": existing.get("status"),
                "explorerUrl": existing.get("explorer_url"),
            }
        prepared = self._prepare(intent, token)
        if self.mode == "prepare":
            return {"status": "prepared", "executionId": intent.idempotency_key, **prepared}

        # Persist the attempt before spending gas. register_broadcast() needs
        # this identity, and the separate executor ledger must retain enough
        # context to recover a hash even if the process exits immediately
        # after eth_sendRawTransaction returns.
        self.runtime.ledger.record_execution_attempt({
            "attempt_id": intent.idempotency_key,
            "idempotency_key": intent.idempotency_key,
            "status": "prepared",
            "side": intent.side,
            "chain_id": intent.chain_id,
            "token_in": intent.token_in,
            "token_out": intent.token_out,
            "amount_in": intent.amount_in,
            "amount_out": prepared.get("expectedOutput"),
            "fly_ids_json": json.dumps(list(intent.fly_ids)),
            "execution_price": token.price_native,
            "gas": prepared.get("estimatedGas"),
            "slippage": intent.slippage_tolerance,
            "tx_hash": None,
            "nonce": prepared.get("transaction", {}).get("nonce"),
            "error": None,
            "created_ms": intent.created_at_ms,
            "updated_ms": int(time.time() * 1000),
        })
        tx_hash = self._broadcast(prepared["transaction"], intent, token)
        self.runtime.ledger.record_execution_attempt({
            "attempt_id": intent.idempotency_key,
            "idempotency_key": intent.idempotency_key,
            "status": "BROADCAST",
            "side": intent.side,
            "chain_id": intent.chain_id,
            "token_in": intent.token_in,
            "token_out": intent.token_out,
            "amount_in": intent.amount_in,
            "amount_out": prepared.get("expectedOutput"),
            "fly_ids_json": json.dumps(list(intent.fly_ids)),
            "execution_price": token.price_native,
            "gas": prepared.get("estimatedGas"),
            "slippage": intent.slippage_tolerance,
            "tx_hash": tx_hash,
            "nonce": None,
            "error": None,
            "created_ms": intent.created_at_ms,
            "updated_ms": int(time.time() * 1000),
        })
        self.runtime.tokens_by_address[(token.chain_id, token.address.lower())] = token
        registration_error: str | None = None
        try:
            self.runtime.record_broadcast(
                intent,
                token,
                tx_hash,
                expected_output=prepared.get("expectedOutput"),
                biological_event_id=intent.biological_event_id,
                wallet_before_native_wei=prepared.get("walletBeforeNativeWei"),
            )
        except Exception as exc:
            # A real hash must remain visible even if the local execution cache
            # is unavailable. The shared queue record below is the recovery
            # handoff used by the brain service and will reconcile from RPC.
            registration_error = str(exc)
        if self.shared_queue is not None:
            try:
                # Make the real hash visible to the brain service immediately;
                # the final receipt transition is written below after polling.
                result = {
                    "status": "BROADCAST",
                    "executionId": intent.idempotency_key,
                    "txHash": tx_hash,
                    "expectedOutput": prepared.get("expectedOutput"),
                }
                if registration_error:
                    result["registrationError"] = registration_error
                self.shared_queue.finish(
                    intent.idempotency_key,
                    "broadcast",
                    result=result,
                )
            except Exception:
                # The local executor ledger and RPC receipt remain canonical;
                # the queue can be refreshed by the final finish below.
                pass
        status, receipt = self._wait_for_receipt(tx_hash)
        self.runtime.snapshot()
        result = {"status": status, "executionId": intent.idempotency_key, "txHash": tx_hash, "receipt": receipt, "expectedOutput": prepared.get("expectedOutput")}
        if registration_error:
            result["registrationError"] = registration_error
        return result

    def _prepare(self, intent: ExecutionIntent, token: TokenRef) -> dict[str, Any]:
        wallet = self.wallet.snapshot()
        if wallet.chain_id != intent.chain_id:
            raise WalletRpcError(f"wallet RPC chain {wallet.chain_id} does not match intent chain {intent.chain_id}")
        if self.api_client is not None:
            try:
                return self._prepare_with_api(intent, token, wallet)
            except UniswapApiError as api_error:
                # A hosted API outage must not turn every biological decision
                # into a permanent dead slot.  Fall back only to the direct
                # RPC route, which still requires a real deployed V2/V3 pool
                # and therefore cannot manufacture a fill for an unroutable
                # token.
                try:
                    return self._prepare_direct(intent, token, wallet)
                except Exception as direct_error:
                    raise WalletRpcError(f"Uniswap API unavailable ({api_error}); direct route unavailable ({direct_error})") from direct_error
        return self._prepare_direct(intent, token, wallet)

    def _prepare_direct(self, intent: ExecutionIntent, token: TokenRef, wallet: Any) -> dict[str, Any]:
        client = self.direct_client
        quote = client.quote(token_in=intent.token_in, token_out=intent.token_out, amount_in=_int_value(intent.amount_in))
        if intent.token_in.lower() != ZERO_ADDRESS.lower():
            token_balance = self.wallet.erc20_balance_raw(intent.token_in)
            if token_balance < _int_value(intent.amount_in):
                raise WalletRpcError("insufficient token balance for sell")
            allowance = client.allowance(intent.token_in, wallet.wallet_address, route_kind=quote.kind)
            if allowance < _int_value(intent.amount_in):
                approval = client.approval_transaction(intent.token_in, _int_value(intent.amount_in), route_kind=quote.kind)
                if self.mode == "prepare":
                    raise RuntimeError("token approval transaction is required before the swap")
                approval_tx = _transaction_from_swap(approval)
                approval_hash = self._broadcast(approval_tx, intent, token)
                approval_status, _ = self._wait_for_receipt(approval_hash)
                if approval_status != "CONFIRMED":
                    raise RuntimeError(f"approval transaction {approval_hash} ended {approval_status}")
        swap = client.build_swap(quote, recipient=wallet.wallet_address, slippage_tolerance=intent.slippage_tolerance)
        transaction = _transaction_from_swap(swap)
        gas_hex = self.wallet.call("eth_estimateGas", [_rpc_transaction(transaction, wallet.wallet_address), "latest"])
        transaction["gas"] = _int_value(gas_hex)
        gas_price_hex = self.wallet.call("eth_gasPrice", [])
        gas_price = _int_value(gas_price_hex)
        native_input = _int_value(intent.amount_in) if intent.token_in.lower() == ZERO_ADDRESS.lower() else 0
        required = native_input + transaction["gas"] * gas_price + wallet.gas_reserve_wei
        if required > wallet.native_balance_wei:
            raise WalletRpcError("input plus estimated gas would consume the gas reserve")
        return {"transaction": transaction, "quote": quote.as_dict(), "swap": swap, "estimatedGas": transaction["gas"], "gasPrice": gas_price, "expectedOutput": str(quote.amount_out), "walletBeforeNativeWei": wallet.native_balance_wei}

    def _prepare_with_api(self, intent: ExecutionIntent, token: TokenRef, wallet: Any) -> dict[str, Any]:
        amount_in = _int_value(intent.amount_in)
        if intent.token_in.lower() == ZERO_ADDRESS.lower() and amount_in > wallet.available_native_wei:
            raise WalletRpcError("insufficient native balance after gas reserve")

        # The backend uses Uniswap's proxy-approval compatibility flow. It
        # returns ordinary approval calldata and keeps the permit signature
        # out of the autonomous runner.
        if intent.token_in.lower() != ZERO_ADDRESS.lower():
            approval_response = self.api_client.check_approval_for_swap(
                wallet_address=wallet.wallet_address,
                token=intent.token_in,
                amount=amount_in,
                chain_id=intent.chain_id,
            )
            cancel = approval_response.get("cancel")
            approval = approval_response.get("approval")
            if isinstance(cancel, Mapping) and self.mode == "prepare":
                return {"status": "approval_cancel_required", "approval": _transaction_from_swap(cancel), "approvalSource": "uniswap-api", "walletBeforeNativeWei": wallet.native_balance_wei}
            if isinstance(cancel, Mapping):
                cancel_hash = self._broadcast(_transaction_from_swap(cancel), intent, token)
                cancel_status, _ = self._wait_for_receipt(cancel_hash)
                if cancel_status != "CONFIRMED":
                    raise RuntimeError(f"approval cancellation transaction {cancel_hash} ended {cancel_status}")
            if isinstance(approval, Mapping):
                if self.mode == "prepare":
                    return {"status": "approval_required", "approval": _transaction_from_swap(approval), "approvalSource": "uniswap-api", "walletBeforeNativeWei": wallet.native_balance_wei}
                approval_tx = _transaction_from_swap(approval)
                approval_hash = self._broadcast(approval_tx, intent, token)
                approval_status, _ = self._wait_for_receipt(approval_hash)
                if approval_status != "CONFIRMED":
                    raise RuntimeError(f"approval transaction {approval_hash} ended {approval_status}")

        quote = self.api_client.quote_exact_input(
            swapper=wallet.wallet_address,
            token_in=intent.token_in,
            token_out=intent.token_out,
            chain_id=intent.chain_id,
            amount_in=amount_in,
            slippage_tolerance=intent.slippage_tolerance,
        )
        swap = self.api_client.create_swap_transaction(quote)
        api_from = swap.get("from")
        if api_from and str(api_from).lower() != wallet.wallet_address.lower():
            raise WalletRpcError("Uniswap API transaction sender does not match the strategy wallet")
        api_chain_id = swap.get("chainId")
        if api_chain_id is not None and _int_value(api_chain_id) != wallet.chain_id:
            raise WalletRpcError("Uniswap API transaction chain does not match the wallet RPC chain")
        transaction = _transaction_from_swap(swap)
        if not isinstance(transaction.get("data"), str) or transaction["data"] in {"", "0x"}:
            raise WalletRpcError("Uniswap API returned empty transaction calldata")
        try:
            estimated_gas = self.wallet.call("eth_estimateGas", [_rpc_transaction(transaction, wallet.wallet_address), "latest"])
        except Exception as exc:
            raise WalletRpcError(f"gas estimation failed: {exc}") from exc
        transaction["gas"] = _int_value(estimated_gas)
        gas_price = _int_value(self.wallet.call("eth_gasPrice", []))
        native_input = amount_in if intent.token_in.lower() == ZERO_ADDRESS.lower() else 0
        required = native_input + transaction["gas"] * gas_price + wallet.gas_reserve_wei
        if required > wallet.native_balance_wei:
            raise WalletRpcError("input plus estimated gas would consume the gas reserve")
        return {"transaction": transaction, "quote": quote.as_dict(), "swap": swap, "estimatedGas": transaction["gas"], "gasPrice": gas_price, "expectedOutput": str(quote.amount_out), "walletBeforeNativeWei": wallet.native_balance_wei}

    def _broadcast(self, transaction: Mapping[str, Any], intent: ExecutionIntent, token: TokenRef) -> str:
        wallet = self.wallet.snapshot()
        try:
            from eth_account import Account
        except ImportError as exc:
            raise RuntimeError("install the fund dependencies to enable signing") from exc
        private_key = os.getenv("PRIVATE_KEY", "").strip()
        if not private_key:
            raise RuntimeError("PRIVATE_KEY is required only by the separately run executor")
        account = Account.from_key(private_key)
        if account.address.lower() != wallet.wallet_address.lower():
            raise RuntimeError("PRIVATE_KEY does not control FUND_WALLET_ADDRESS")
        tx = dict(transaction)
        tx["chainId"] = wallet.chain_id
        tx["nonce"] = _int_value(self.wallet.call("eth_getTransactionCount", [wallet.wallet_address, "pending"]))
        if "maxFeePerGas" not in tx and "maxPriorityFeePerGas" not in tx:
            tx.setdefault("gasPrice", _int_value(self.wallet.call("eth_gasPrice", [])))
        tx.setdefault("gas", _int_value(self.wallet.call("eth_estimateGas", [_rpc_transaction(tx, wallet.wallet_address), "latest"])))
        signed = Account.sign_transaction(tx, private_key)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        if raw is None:
            raise RuntimeError("signer did not return raw transaction bytes")
        return self.wallet.send_raw_transaction("0x" + bytes(raw).hex())

    def _wait_for_receipt(self, tx_hash: str) -> tuple[str, dict[str, Any] | None]:
        timeout = max(1.0, float(os.getenv("FUND_RUNNER_RECEIPT_TIMEOUT_SECONDS", "120")))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            receipt = self.wallet.call("eth_getTransactionReceipt", [tx_hash])
            if isinstance(receipt, Mapping) and receipt.get("status") is not None:
                return ("CONFIRMED" if _int_value(receipt["status"]) == 1 else "REVERTED"), dict(receipt)
            time.sleep(min(3.0, max(0.25, deadline - time.monotonic())))
        return "PENDING", None

def main() -> int:
    load_project_env()
    parser = argparse.ArgumentParser(description="Consume FruitFly execution intents and run Uniswap swaps")
    parser.add_argument("--backend", choices=("file", "supabase"), default=os.getenv("FUND_INTENT_QUEUE_BACKEND", os.getenv("FUND_ADAPTER", "file")))
    parser.add_argument("--queue", default=os.getenv("FUND_INTENT_QUEUE_PATH", "data/fund/execution-intents.jsonl"))
    parser.add_argument("--mode", choices=("prepare", "broadcast"), default=os.getenv("FUND_RUNNER_MODE", "prepare"))
    parser.add_argument("--once", action="store_true", help="process currently queued items and exit")
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("FUND_RUNNER_POLL_SECONDS", "1")))
    args = parser.parse_args()
    os.environ["FUND_INTENT_QUEUE_BACKEND"] = args.backend
    queue = SupabaseIntentQueue.from_env() if args.backend == "supabase" else None
    if args.backend == "supabase" and queue is None:
        print(json.dumps({"status": "startup_error", "error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --backend supabase"}), file=sys.stderr)
        return 2
    try:
        executor = TradeExecutor(args.mode, shared_queue=queue)
    except Exception as exc:
        print(json.dumps({"status": "startup_error", "error": str(exc)}), file=sys.stderr)
        return 2
    worker_id = SupabaseIntentQueue.new_worker_id() if queue is not None else "file-worker"
    queue_path = Path(args.queue)
    offset_path = Path(os.getenv("FUND_RUNNER_OFFSET_PATH", f"{queue_path}.offset"))
    offset = int(offset_path.read_text(encoding="utf-8").strip() or "0") if offset_path.exists() else 0
    print(json.dumps({"status": "ready", "backend": args.backend, "mode": args.mode, "workerId": worker_id}, sort_keys=True), flush=True)
    last_wait_log = 0.0
    health_url = _brain_health_url() if queue is not None else ""
    emergency_enabled = os.getenv("FUND_EMERGENCY_SELL_ON_SERVER_DOWN", "false").lower() == "true"
    outage_after_seconds = max(30.0, float(os.getenv("FUND_BRAIN_OUTAGE_SELL_AFTER_SECONDS", "120")))
    health_poll_seconds = max(5.0, float(os.getenv("FUND_BRAIN_HEALTH_POLL_SECONDS", "15")))
    last_health_check = 0.0
    outage_started_at: float | None = None
    emergency_incident_id: str | None = None
    while True:
        if queue is not None:
            now = time.monotonic()
            if health_url and not args.once and now - last_health_check >= health_poll_seconds:
                last_health_check = now
                healthy = _brain_is_healthy(health_url)
                if healthy:
                    if outage_started_at is not None:
                        print(json.dumps({"status": "brain_recovered", "healthUrl": health_url}, sort_keys=True), flush=True)
                    outage_started_at = None
                    emergency_incident_id = None
                else:
                    outage_started_at = outage_started_at if outage_started_at is not None else now
                    outage_age = now - outage_started_at
                    if (
                        emergency_enabled
                        and args.mode == "broadcast"
                        and os.getenv("FUND_RUNNER_CONFIRM_BROADCAST", "false").lower() == "true"
                        and outage_age >= outage_after_seconds
                        and emergency_incident_id is None
                    ):
                        emergency_incident_id = f"{int(time.time())}"
                        try:
                            recovery = executor.emergency_sell_confirmed_holdings(queue, incident_id=emergency_incident_id)
                            print(json.dumps({"status": "brain_down_emergency_sells", "healthUrl": health_url, "outageSeconds": round(outage_age, 1), "results": recovery}, sort_keys=True), flush=True)
                        except Exception as exc:
                            emergency_incident_id = None
                            print(json.dumps({"status": "emergency_sell_error", "healthUrl": health_url, "error": str(exc)}, sort_keys=True), flush=True)
            try:
                records = queue.claim(worker_id, limit=1)
            except Exception as exc:
                print(json.dumps({"status": "queue_error", "backend": "supabase", "error": str(exc)}, sort_keys=True), flush=True)
                if args.once:
                    return 2
                time.sleep(max(0.1, args.poll_seconds))
                continue
            if not records:
                now = time.monotonic()
                if args.once:
                    print(json.dumps({"status": "no_pending_intents", "backend": "supabase", "workerId": worker_id}, sort_keys=True), flush=True)
                    return 0
                if now - last_wait_log >= 15.0:
                    print(json.dumps({"status": "waiting_for_execution_intents", "backend": "supabase", "workerId": worker_id}, sort_keys=True), flush=True)
                    last_wait_log = now
            for record in records:
                raw_payload = record.get("payload")
                try:
                    intent, token = _load_record(json.dumps(raw_payload))
                    result = executor.process(intent, token)
                    status = "prepared" if args.mode == "prepare" else ("confirmed" if result.get("status") == "CONFIRMED" else "broadcast")
                    queue.finish(intent.idempotency_key, status, result=result)
                    print(json.dumps(result, sort_keys=True), flush=True)
                except Exception as exc:
                    key = str(record.get("idempotency_key") or "")
                    if key:
                        queue.finish(key, "failed", error=str(exc))
                    print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), flush=True)
            if args.once:
                return 0
        elif queue_path.exists():
            with queue_path.open("r", encoding="utf-8") as stream:
                stream.seek(offset)
                for raw in stream:
                    offset = stream.tell()
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        intent, token = _load_record(line)
                        result = executor.process(intent, token)
                        print(json.dumps(result, sort_keys=True), flush=True)
                    except Exception as exc:
                        print(json.dumps({"status": "error", "error": str(exc)}), flush=True)
                offset_path.parent.mkdir(parents=True, exist_ok=True)
                offset_path.write_text(str(offset), encoding="utf-8")
        if args.once:
            return 0
        time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
