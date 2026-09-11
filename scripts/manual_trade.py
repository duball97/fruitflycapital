#!/usr/bin/env python3
"""Reusable manual BUY/SELL command helpers for the FruitFly executor.

The default mode prepares a fresh quote and transaction without signing.
Pass ``--broadcast`` explicitly to sign, submit, and wait for the receipt.
The private key is read only by the existing executor and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from fractions import Fraction
from typing import Any, Mapping

from malecns.config import load_project_env
from malecns.fund.supabase_queue import SupabaseIntentQueue
from malecns.fund.wallet import ZERO_ADDRESS, RpcWalletClient
try:
    from scripts.run_trade_executor import ADDRESS_RE, TradeExecutor, _load_record
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from run_trade_executor import ADDRESS_RE, TradeExecutor, _load_record


WEI_PER_ETH = Decimal(10**18)
SYMBOL_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")


def _positive_decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a positive decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field} must be a positive decimal")
    return parsed


def _parse_fraction(value: str) -> Decimal:
    text = value.strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            fraction = Fraction(int(numerator), int(denominator))
            parsed = Decimal(fraction.numerator) / Decimal(fraction.denominator)
        else:
            parsed = Decimal(text)
    except (InvalidOperation, ValueError, ZeroDivisionError) as exc:
        raise ValueError("fraction must be a positive decimal or a form such as 1/16") from exc
    if not parsed.is_finite() or parsed <= 0 or parsed > 1:
        raise ValueError("fraction must be greater than 0 and no greater than 1")
    return parsed


def _raw_from_decimal(value: Decimal, decimals: int) -> int:
    if decimals < 0 or decimals > 255:
        raise ValueError("token decimals are outside the supported range")
    raw = (value * (Decimal(10) ** decimals)).to_integral_value(rounding=ROUND_DOWN)
    if raw <= 0:
        raise ValueError("amount is too small for the token decimals")
    return int(raw)


def _address(value: str, field: str) -> str:
    if not ADDRESS_RE.fullmatch(value):
        raise ValueError(f"{field} must be a 20-byte 0x-prefixed contract address")
    return value


def _symbol(value: str) -> str:
    if not SYMBOL_RE.fullmatch(value):
        raise ValueError("symbol may contain only letters, numbers, '.', '_' and '-'")
    return value


def _idempotency(value: str | None, side: str, symbol: str) -> str:
    candidate = value or f"manual-{side}-{symbol.lower()}-{time.time_ns()}"
    if not IDEMPOTENCY_RE.fullmatch(candidate):
        raise ValueError("idempotency key contains unsupported characters or is too long")
    return candidate


def _common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--token", required=True, help="20-byte token contract address")
    parser.add_argument("--symbol", help="token symbol used in the execution record")
    parser.add_argument("--slippage", type=float, default=None, help="slippage tolerance percentage; defaults to FUND_SLIPPAGE_TOLERANCE")
    parser.add_argument("--idempotency-key", help="stable retry key; reuse it only for the same intended trade")
    parser.add_argument("--broadcast", action="store_true", help="sign and submit the transaction; without this flag, only prepare")


def _load_args(side: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Prepare or broadcast a FruitFly {side.upper()} swap")
    _common_parser(parser)
    if side == "buy":
        amount = parser.add_mutually_exclusive_group()
        amount.add_argument("--eth", help="exact native ETH amount to spend")
        amount.add_argument("--fraction", default="1/16", help="fraction of current tradeable ETH; default: 1/16")
    else:
        amount = parser.add_mutually_exclusive_group()
        amount.add_argument("--amount", help="human-readable token amount; default: full wallet balance")
        amount.add_argument("--amount-raw", type=int, help="raw integer token amount")
    return parser.parse_args()


def _build_payload(
    *,
    side: str,
    chain_id: int,
    token_address: str,
    symbol: str,
    amount_raw: int,
    idempotency_key: str,
    slippage: float,
) -> dict[str, Any]:
    intent = {
        "idempotencyKey": idempotency_key,
        "side": side,
        "chainId": chain_id,
        "tokenIn": ZERO_ADDRESS if side == "buy" else token_address,
        "tokenOut": token_address if side == "buy" else ZERO_ADDRESS,
        "amountIn": str(amount_raw),
        "flyIds": [],
        "slippageTolerance": slippage,
        "createdAtMs": int(time.time() * 1000),
        "biologicalEventId": idempotency_key,
    }
    return {
        "executionIntent": intent,
        "token": {
            "chainId": chain_id,
            "address": token_address,
            "symbol": symbol,
            "liquidityUsd": None,
            "priceUsd": None,
            "priceNative": None,
        },
        "queuedAtMs": int(time.time() * 1000),
    }


def _recover_after_broadcast_error(executor: TradeExecutor, intent_key: str, error: Exception) -> dict[str, Any] | None:
    """Recover a hash if RPC accepted it but a later step raised."""

    attempt = next(
        (row for row in executor.runtime.ledger.rows("execution_attempts", limit=1000) if row.get("idempotency_key") == intent_key),
        None,
    )
    tx_hash = str(attempt.get("tx_hash") or "") if attempt else ""
    if not tx_hash:
        return None
    status, receipt = executor._wait_for_receipt(tx_hash)
    return {"status": status, "executionId": intent_key, "txHash": tx_hash, "receipt": receipt, "recoveredError": str(error)}


def _summary(result: Mapping[str, Any], *, side: str, symbol: str, chain_id: int, amount_raw: int, decimals: int) -> dict[str, Any]:
    receipt = result.get("receipt") if isinstance(result.get("receipt"), Mapping) else {}
    summary: dict[str, Any] = {
        "status": result.get("status"),
        "side": side,
        "token": symbol,
        "chainId": chain_id,
        "amountInRaw": str(amount_raw),
        "amountIn": str(Decimal(amount_raw) / (Decimal(10) ** decimals)),
    }
    for key in ("txHash", "expectedOutput", "estimatedGas", "gasPrice", "approvalRequired", "recoveredError"):
        if result.get(key) is not None:
            summary[key] = result[key]
    if receipt.get("blockNumber") is not None:
        summary["blockNumber"] = receipt["blockNumber"]
    return summary


def run(side: str) -> int:
    load_project_env()
    args = _load_args(side)
    try:
        token_address = _address(args.token, "--token")
        symbol = _symbol(args.symbol or token_address[:8])
        slippage = float(args.slippage if args.slippage is not None else os.getenv("FUND_SLIPPAGE_TOLERANCE", "0.5"))
        if not 0 <= slippage <= 5:
            raise ValueError("slippage must be between 0 and 5 percent")
        key = _idempotency(args.idempotency_key, side, symbol)
        wallet = RpcWalletClient.from_env()
        if wallet is None:
            raise RuntimeError("FUND_RPC_URL and FUND_WALLET_ADDRESS are required")
        snapshot = wallet.snapshot()

        if side == "buy":
            if args.eth is not None:
                amount_raw = _raw_from_decimal(_positive_decimal(args.eth, "--eth"), 18)
            else:
                fraction = _parse_fraction(args.fraction)
                amount_raw = int((Decimal(snapshot.available_native_wei) * fraction).to_integral_value(rounding=ROUND_DOWN))
            if amount_raw <= 0:
                raise ValueError("the selected buy size is below one wei")
            if amount_raw > snapshot.available_native_wei:
                raise ValueError("buy amount exceeds the wallet balance available after gas reserve")
            decimals = 18
        else:
            balance_raw = wallet.erc20_balance_raw(token_address)
            decimals = wallet.erc20_decimals(token_address)
            if args.amount_raw is not None:
                amount_raw = args.amount_raw
            elif args.amount is not None:
                amount_raw = _raw_from_decimal(_positive_decimal(args.amount, "--amount"), decimals)
            else:
                amount_raw = balance_raw
            if amount_raw <= 0:
                raise ValueError("sell amount must be greater than zero")
            if amount_raw > balance_raw:
                raise ValueError("sell amount exceeds the wallet token balance")

        payload = _build_payload(side=side, chain_id=snapshot.chain_id, token_address=token_address, symbol=symbol, amount_raw=amount_raw, idempotency_key=key, slippage=slippage)
        intent, token = _load_record(json.dumps(payload))
        if args.broadcast:
            os.environ["FUND_RUNNER_CONFIRM_BROADCAST"] = "true"
        executor = TradeExecutor("broadcast" if args.broadcast else "prepare", shared_queue=None)
        try:
            result = executor.process(intent, token)
        except Exception as exc:
            if not args.broadcast:
                raise
            result = _recover_after_broadcast_error(executor, key, exc)
            if result is None:
                raise

        if args.broadcast:
            queue = SupabaseIntentQueue.from_env()
            if queue is not None:
                queue.enqueue(payload)
                queue.finish(key, "confirmed" if result.get("status") == "CONFIRMED" else "broadcast", result=result)
        print(json.dumps(_summary(result, side=side, symbol=symbol, chain_id=snapshot.chain_id, amount_raw=amount_raw, decimals=decimals), sort_keys=True))
        return 0 if result.get("status") not in {"REVERTED", "error"} else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "side": side, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


def main_buy() -> int:
    return run("buy")


def main_sell() -> int:
    return run("sell")
