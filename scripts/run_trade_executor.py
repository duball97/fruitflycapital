#!/usr/bin/env python3
"""Run the separate FruitFly execution service.

The brain server publishes netted ExecutionIntent records when
``FUND_ADAPTER=queue``. This process consumes those records, requests a
Uniswap quote, handles approval transactions when needed, and can either
prepare or broadcast the transaction.

Examples:
    PYTHONPATH=src .venv/bin/python scripts/run_trade_executor.py --once
    FUND_RUNNER_CONFIRM_BROADCAST=true \
      PYTHONPATH=src .venv/bin/python scripts/run_trade_executor.py --mode broadcast
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from malecns.config import load_project_env
from malecns.fund.autonomous import AutonomousTradingRuntime, ExecutionIntent, TokenRef
from malecns.fund.ledger import FundLedger
from malecns.fund.wallet import ZERO_ADDRESS, RpcWalletClient, WalletRpcError
from malecns.market.uniswap_client import UniswapTradingClient
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


class TradeExecutor:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        # This process is the autonomous execution client. The brain server
        # can keep its default human-mediated header when it is only quoting.
        os.environ.setdefault("UNISWAP_DECISION_ORIGIN", "autonomous")
        self.wallet = RpcWalletClient.from_env()
        self.client = UniswapTradingClient.from_env()
        if self.wallet is None:
            raise RuntimeError("FUND_RPC_URL and FUND_WALLET_ADDRESS are required")
        if self.client is None:
            raise RuntimeError("UNISWAP_API_KEY is required")
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
        tx_hash = self._broadcast(prepared["transaction"], intent, token)
        self.runtime.tokens_by_address[(token.chain_id, token.address.lower())] = token
        registered = self.runtime.register_broadcast(
            intent.idempotency_key,
            tx_hash,
            expected_output=prepared.get("expectedOutput"),
            biological_event_id=intent.biological_event_id,
            wallet_before_native_wei=prepared.get("walletBeforeNativeWei"),
        )
        if not registered:
            raise RuntimeError("broadcast succeeded but the execution record could not be registered")
        status, receipt = self._wait_for_receipt(tx_hash)
        self.runtime.snapshot()
        return {"status": status, "executionId": intent.idempotency_key, "txHash": tx_hash, "receipt": receipt, "expectedOutput": prepared.get("expectedOutput")}

    def _prepare(self, intent: ExecutionIntent, token: TokenRef) -> dict[str, Any]:
        wallet = self.wallet.snapshot()
        if wallet.chain_id != intent.chain_id:
            raise WalletRpcError(f"wallet RPC chain {wallet.chain_id} does not match intent chain {intent.chain_id}")
        minimum_liquidity = float(os.getenv("FUND_MIN_LIQUIDITY_USD", "0"))
        if token.liquidity_usd is None or token.liquidity_usd < minimum_liquidity:
            raise WalletRpcError("token does not meet the configured minimum liquidity")
        if intent.token_in.lower() != ZERO_ADDRESS.lower():
            token_balance = self.wallet.erc20_balance_raw(intent.token_in)
            if token_balance < _int_value(intent.amount_in):
                raise WalletRpcError("insufficient token balance for sell")
            approval_response = self.client.check_approval({"walletAddress": wallet.wallet_address, "token": intent.token_in, "amount": intent.amount_in, "chainId": intent.chain_id, "tokenOut": intent.token_out, "tokenOutChainId": intent.chain_id})
            approval = approval_response.get("approval") or approval_response.get("approvalTransaction")
            if approval is not None:
                if self.mode == "prepare":
                    raise RuntimeError("token approval transaction is required before the swap")
                approval_tx = _transaction_from_swap(approval)
                approval_hash = self._broadcast(approval_tx, intent, token)
                approval_status, _ = self._wait_for_receipt(approval_hash)
                if approval_status != "CONFIRMED":
                    raise RuntimeError(f"approval transaction {approval_hash} ended {approval_status}")
        quote = self.client.quote({"swapper": wallet.wallet_address, "tokenIn": intent.token_in, "tokenOut": intent.token_out, "tokenInChainId": str(intent.chain_id), "tokenOutChainId": str(intent.chain_id), "amount": intent.amount_in, "type": "EXACT_INPUT", "slippageTolerance": intent.slippage_tolerance})
        swap = self.client.create_unsigned_swap(quote)
        transaction = _transaction_from_swap(swap)
        gas_hex = self.wallet.call("eth_estimateGas", [_rpc_transaction(transaction, wallet.wallet_address), "latest"])
        transaction["gas"] = _int_value(gas_hex)
        gas_price_hex = self.wallet.call("eth_gasPrice", [])
        gas_price = _int_value(gas_price_hex)
        native_input = _int_value(intent.amount_in) if intent.token_in.lower() == ZERO_ADDRESS.lower() else 0
        required = native_input + transaction["gas"] * gas_price + wallet.gas_reserve_wei
        if required > wallet.native_balance_wei:
            raise WalletRpcError("input plus estimated gas would consume the gas reserve")
        return {"transaction": transaction, "quote": quote, "swap": swap, "estimatedGas": transaction["gas"], "gasPrice": gas_price, "expectedOutput": self._expected_output(quote), "walletBeforeNativeWei": wallet.native_balance_wei}

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

    @staticmethod
    def _expected_output(quote: Mapping[str, Any]) -> str | None:
        raw_quote = quote.get("quote") if isinstance(quote.get("quote"), Mapping) else quote
        if not isinstance(raw_quote, Mapping):
            return None
        output = raw_quote.get("output")
        if isinstance(output, Mapping) and output.get("amount") is not None:
            return str(output["amount"])
        order_info = raw_quote.get("orderInfo")
        if isinstance(order_info, Mapping) and isinstance(order_info.get("outputs"), list) and order_info["outputs"]:
            first = order_info["outputs"][0]
            if isinstance(first, Mapping) and first.get("startAmount") is not None:
                return str(first["startAmount"])
        return None


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
    try:
        executor = TradeExecutor(args.mode)
    except Exception as exc:
        print(json.dumps({"status": "startup_error", "error": str(exc)}), file=sys.stderr)
        return 2
    queue = SupabaseIntentQueue.from_env() if args.backend == "supabase" else None
    if args.backend == "supabase" and queue is None:
        print(json.dumps({"status": "startup_error", "error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --backend supabase"}), file=sys.stderr)
        return 2
    worker_id = SupabaseIntentQueue.new_worker_id() if queue is not None else "file-worker"
    queue_path = Path(args.queue)
    offset_path = Path(os.getenv("FUND_RUNNER_OFFSET_PATH", f"{queue_path}.offset"))
    offset = int(offset_path.read_text(encoding="utf-8").strip() or "0") if offset_path.exists() else 0
    print(json.dumps({"status": "ready", "backend": args.backend, "mode": args.mode, "workerId": worker_id}, sort_keys=True), flush=True)
    while True:
        if queue is not None:
            try:
                records = queue.claim(worker_id, limit=1)
            except Exception as exc:
                print(json.dumps({"status": "queue_error", "backend": "supabase", "error": str(exc)}, sort_keys=True), flush=True)
                if args.once:
                    return 2
                time.sleep(max(0.1, args.poll_seconds))
                continue
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
