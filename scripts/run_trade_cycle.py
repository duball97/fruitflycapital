#!/usr/bin/env python3
"""Prepare or interactively broadcast a FruitFly rebalance cycle.

Recurring operation is always prepare-only. A single cycle may be broadcast
only with --once --broadcast, with a terminal confirmation before each trade.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import os
import random
import subprocess
import sys
import time

from malecns.config import load_project_env
from malecns.fund.wallet import RpcWalletClient


def _addresses() -> list[str]:
    values = os.getenv("NEUROSWARM_MARKET_DISCOVERY_TOKEN_ADDRESSES", "").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        address = value.strip()
        key = address.lower()
        if len(address) == 42 and address.startswith("0x") and key not in seen:
            seen.add(key)
            result.append(address)
    return result


def _run_prepare(script: str, address: str, symbol: str, extra: list[str], *, broadcast: bool) -> int:
    command = [sys.executable, f"scripts/{script}", "--token", address, "--symbol", symbol, *extra]
    if broadcast:
        answer = input(f"Broadcast this {script.removesuffix('_token.py')} trade now? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("skipped")
            return 0
        command.append("--broadcast")
    print("$", " ".join(command))
    completed = subprocess.run(command, check=False)
    return completed.returncode


def run_cycle(
    wallet: RpcWalletClient,
    *,
    buy_fraction: str,
    max_buys: int,
    max_sells: int,
    broadcast: bool,
) -> None:
    addresses = _addresses()
    if not addresses:
        raise RuntimeError("NEUROSWARM_MARKET_DISCOVERY_TOKEN_ADDRESSES is empty")

    held: list[tuple[str, int]] = []
    for address in addresses:
        try:
            balance = wallet.erc20_balance_raw(address)
        except Exception as exc:
            print(f"balance check skipped for {address}: {exc}", file=sys.stderr)
            continue
        if balance > 0:
            held.append((address, balance))

    held_keys = {address.lower() for address, _ in held}
    candidates = [address for address in addresses if address.lower() not in held_keys]
    if not candidates:
        candidates = addresses

    snapshot = wallet.snapshot()
    per_fly_wei = int((Decimal(snapshot.available_native_wei) / Decimal(16)).to_integral_value())
    if per_fly_wei <= 0:
        raise RuntimeError("available ETH is below one 1/16 per-fly budget")
    per_fly_eth = format(Decimal(per_fly_wei) / Decimal(10**18), "f")

    rng = random.SystemRandom()
    buy_count = rng.randint(1, min(max_buys, len(candidates)))
    sell_count = rng.randint(0, min(max_sells, len(held)))
    selected = rng.sample(candidates, buy_count)
    sell_targets = rng.sample(held, sell_count)

    print("PREPARE-ONLY CYCLE")
    print(f"selected random buy contracts: {', '.join(selected)}")
    print(f"each buy size: 1/16 of deployable ETH ({per_fly_eth} ETH)")
    print(f"random sells this cycle: {sell_count}")

    for address, balance_raw in sell_targets:
        sell_amount_raw = max(1, balance_raw // 16)
        _run_prepare(
            "sell_token.py",
            address,
            address[:8],
            ["--amount-raw", str(sell_amount_raw)],
            broadcast=broadcast,
        )
    for address in selected:
        _run_prepare("buy_token.py", address, address[:8], ["--eth", per_fly_eth], broadcast=broadcast)
    if not broadcast:
        print("No transaction was broadcast. Review each prepared result and run the existing manual command explicitly.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare recurring or interactively broadcast one FruitFly trade cycle")
    parser.add_argument("--min-interval-seconds", type=float, default=900, help="minimum delay between cycles (default: 900)")
    parser.add_argument("--max-interval-seconds", type=float, default=2700, help="maximum delay between cycles (default: 2700)")
    parser.add_argument("--buy-fraction", default="1/16", help="retained for compatibility; each buy is fixed at 1/16")
    parser.add_argument("--max-buys", type=int, default=3, help="maximum random buys per cycle (default: 3)")
    parser.add_argument("--max-sells", type=int, default=3, help="maximum random sells per cycle (default: 3)")
    parser.add_argument("--once", action="store_true", help="prepare one cycle and exit")
    parser.add_argument("--broadcast", action="store_true", help="interactively broadcast one cycle; requires --once")
    args = parser.parse_args()
    if args.min_interval_seconds <= 0 or args.max_interval_seconds < args.min_interval_seconds:
        parser.error("interval bounds must be positive and max must be >= min")
    if args.max_buys < 1 or args.max_sells < 0:
        parser.error("--max-buys must be positive and --max-sells cannot be negative")
    if args.broadcast and not args.once:
        parser.error("--broadcast requires --once; recurring unattended broadcasting is disabled")
    load_project_env()
    wallet = RpcWalletClient.from_env()
    if wallet is None:
        print("FUND_RPC_URL and FUND_WALLET_ADDRESS are required", file=sys.stderr)
        return 2

    while True:
        try:
            run_cycle(
                wallet,
                buy_fraction=args.buy_fraction,
                max_buys=args.max_buys,
                max_sells=args.max_sells,
                broadcast=args.broadcast,
            )
        except KeyboardInterrupt:
            print("stopped")
            return 0
        except Exception as exc:
            print(f"cycle error: {exc}", file=sys.stderr)
            if args.once:
                return 1
        if args.once:
            return 0
        delay = random.SystemRandom().uniform(args.min_interval_seconds, args.max_interval_seconds)
        print(f"next prepare cycle in {delay:.0f} seconds")
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
