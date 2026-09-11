#!/usr/bin/env python3
"""Prepare or broadcast a FruitFly rebalance cycle.

Recurring operation can now optionally broadcast. Use --once for a single cycle.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import os
import random
import subprocess
import sys
import time
import traceback

from malecns.config import load_project_env
from malecns.fund.wallet import RpcWalletClient


def _addresses() -> list[str]:
    values = os.getenv("NEUROSWARM_MARKET_DISCOVERY_TOKEN_ADDRESSES", "")
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values.split(","):
        address = value.strip()
        key = address.lower()
        if len(address) == 42 and address.startswith("0x") and key not in seen:
            seen.add(key)
            result.append(address)
    return result


def _run_prepare(script: str, address: str, symbol: str, extra: list[str], *, broadcast: bool) -> int:
    try:
        command = [sys.executable, f"scripts/{script}", "--token", address, "--symbol", symbol, *extra]
        if broadcast:
            command.append("--broadcast")
        print("$", " ".join(command))
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            print(f"ERROR: {script} failed for {address}: {completed.stderr}", file=sys.stderr)
        return completed.returncode
    except Exception as exc:
        print(f"ERROR: Failed to run {script} for {address}: {exc}", file=sys.stderr)
        return 1


def _token_symbol(wallet: RpcWalletClient, address: str) -> str:
    try:
        symbol = wallet.erc20_symbol(address)
        if symbol and not symbol.lower().startswith("0x"):
            return symbol
    except Exception:
        pass
    return address[:8]


def run_cycle(
    wallet: RpcWalletClient,
    *,
    buy_fraction: str,
    max_buys: int,
    max_sells: int,
    broadcast: bool,
) -> None:
    try:
        addresses = _addresses()
        if not addresses:
            print("WARNING: NEUROSWARM_MARKET_DISCOVERY_TOKEN_ADDRESSES is empty", file=sys.stderr)
            return

        held: list[tuple[str, int]] = []
        for address in addresses:
            try:
                balance = wallet.erc20_balance_raw(address)
                if balance > 0:
                    held.append((address, balance))
            except Exception as exc:
                print(f"WARNING: balance check skipped for {address}: {exc}", file=sys.stderr)
                continue

        held_keys = {address.lower() for address, _ in held}
        candidates = [address for address in addresses if address.lower() not in held_keys]
        
        if not candidates and held:
            print("All tokens held—must sell to free up buying capacity")
            candidates = addresses

        try:
            snapshot = wallet.snapshot()
            per_fly_wei = int((Decimal(snapshot.available_native_wei) / Decimal(16)).to_integral_value())
        except Exception as exc:
            print(f"ERROR: Failed to get wallet snapshot: {exc}", file=sys.stderr)
            per_fly_wei = 0
        
        eth_low = per_fly_wei <= 0 or len(held) > 5
        
        if per_fly_wei <= 0:
            print("WARNING: No ETH available for buys—selling mode only", file=sys.stderr)
            per_fly_eth = "0"
        else:
            per_fly_eth = format(Decimal(per_fly_wei) / Decimal(10**18), "f")

        rng = random.SystemRandom()
        
        if held:
            min_sells = 1 if not eth_low else min(2, len(held))
            sell_count = rng.randint(min_sells, min(max_sells, len(held)))
        else:
            sell_count = 0
        
        buy_count = rng.randint(1, min(max_buys, len(candidates))) if candidates and per_fly_wei > 0 else 0
        
        try:
            selected = rng.sample(candidates, buy_count) if candidates else []
            sell_targets = rng.sample(held, sell_count) if held else []
        except ValueError as exc:
            print(f"ERROR: Sampling failed: {exc}", file=sys.stderr)
            selected = []
            sell_targets = []

        if broadcast:
            print("BROADCAST CYCLE")
        else:
            print("PREPARE-ONLY CYCLE")
        
        if sell_targets:
            print(f"selling {len(sell_targets)} full positions to free up ETH")
        if selected:
            print(f"selected random buy contracts: {', '.join(selected)}")
            print(f"each buy size: 1/16 of deployable ETH ({per_fly_eth} ETH)")
        elif per_fly_wei <= 0:
            print("no buys possible—insufficient ETH")

        for address, balance_raw in sell_targets:
            try:
                _run_prepare(
                    "sell_token.py",
                    address,
                    _token_symbol(wallet, address),
                    ["--amount-raw", str(balance_raw)],
                    broadcast=broadcast,
                )
            except Exception as exc:
                print(f"ERROR: Sell failed for {address}: {exc}", file=sys.stderr)
                
        for address in selected:
            try:
                _run_prepare("buy_token.py", address, _token_symbol(wallet, address), ["--eth", per_fly_eth], broadcast=broadcast)
            except Exception as exc:
                print(f"ERROR: Buy failed for {address}: {exc}", file=sys.stderr)
                
        if not broadcast:
            print("No transaction was broadcast. Review each prepared result and run the existing manual command explicitly.")
            
    except Exception as exc:
        print(f"ERROR: Cycle failed: {exc}", file=sys.stderr)
        traceback.print_exc()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or broadcast FruitFly trade cycles")
    parser.add_argument("--min-interval-seconds", type=float, default=180, help="minimum delay between cycles in seconds (default: 180)")
    parser.add_argument("--max-interval-seconds", type=float, default=420, help="maximum delay between cycles in seconds (default: 420)")
    parser.add_argument("--buy-fraction", default="1/16", help="retained for compatibility; each buy is fixed at 1/16")
    parser.add_argument("--max-buys", type=int, default=3, help="maximum random buys per cycle (default: 3)")
    parser.add_argument("--max-sells", type=int, default=3, help="maximum random sells per cycle (default: 3)")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--broadcast", action="store_true", help="broadcast transactions (default: prepare-only)")
    args = parser.parse_args()
    
    if args.min_interval_seconds <= 0 or args.max_interval_seconds < args.min_interval_seconds:
        parser.error("interval bounds must be positive and max must be >= min")
    if args.max_buys < 1 or args.max_sells < 0:
        parser.error("--max-buys must be positive and --max-sells cannot be negative")
    
    try:
        load_project_env()
    except Exception as exc:
        print(f"ERROR: Failed to load project env: {exc}", file=sys.stderr)
        return 1
    
    try:
        wallet = RpcWalletClient.from_env()
        if wallet is None:
            print("ERROR: FUND_RPC_URL and FUND_WALLET_ADDRESS are required", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"ERROR: Failed to initialize wallet: {exc}", file=sys.stderr)
        return 2

    cycle_count = 0
    while True:
        cycle_count += 1
        print(f"\n=== Cycle {cycle_count} ===")
        
        try:
            run_cycle(
                wallet,
                buy_fraction=args.buy_fraction,
                max_buys=args.max_buys,
                max_sells=args.max_sells,
                broadcast=args.broadcast,
            )
        except KeyboardInterrupt:
            print("\nstopped by user")
            return 0
        except Exception as exc:
            print(f"CRITICAL ERROR in cycle {cycle_count}: {exc}", file=sys.stderr)
            traceback.print_exc()
            print("Continuing to next cycle...", file=sys.stderr)
            
        if args.once:
            print("Single cycle complete (--once specified)")
            return 0
            
        delay = random.SystemRandom().uniform(args.min_interval_seconds, args.max_interval_seconds)
        minutes = delay / 60
        print(f"Next cycle in {minutes:.1f} minutes...")
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
