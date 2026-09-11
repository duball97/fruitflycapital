"""Post-broadcast Robinhood Chain receipt and Blockscout verification.

This module starts at a real transaction hash. It never creates hashes and it
never treats a simulation identifier as a mainnet execution. The JSON-RPC
receipt is canonical; Blockscout is an optional presentation/enrichment layer.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Mapping
from urllib.parse import urlencode


ROBINHOOD_CHAIN_ID = 4663
ROBINHOOD_EXPLORER_URL = "https://robinhoodchain.blockscout.com"
TX_HASH_RE = r"^0x[a-fA-F0-9]{64}$"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class ReceiptStatus:
    BROADCAST = "BROADCAST"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REVERTED = "REVERTED"


JsonFetcher = Callable[[str, float], Any]


@dataclass
class BlockscoutClient:
    """Small cached public metadata client; failures are deliberately soft."""

    base_url: str = ROBINHOOD_EXPLORER_URL
    timeout_seconds: float = 8.0
    fetcher: JsonFetcher | None = None
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _wallet_history_cache: dict[str, tuple[float, list[dict[str, Any]]]] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def from_env(cls) -> "BlockscoutClient":
        return cls(
            base_url=os.getenv("FUND_EXPLORER_URL", ROBINHOOD_EXPLORER_URL).strip() or ROBINHOOD_EXPLORER_URL,
            timeout_seconds=float(os.getenv("BLOCKSCOUT_TIMEOUT_SECONDS", "8")),
        )

    def transaction(self, tx_hash: str) -> dict[str, Any]:
        cached = self._cache.get(tx_hash.lower())
        if cached is not None:
            return cached
        url = f"{self.base_url.rstrip('/')}/api/v2/transactions/{tx_hash}"
        try:
            payload = self.fetcher(url, self.timeout_seconds) if self.fetcher else self._request(url)
        except Exception as exc:
            raise RuntimeError(f"Blockscout request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Blockscout returned a non-object response")
        self._cache[tx_hash.lower()] = payload
        return payload

    def wallet_trade_history(self, wallet_address: str, *, chain_id: int = ROBINHOOD_CHAIN_ID) -> list[dict[str, Any]]:
        """Return buy/sell legs for every indexed transaction sent by a wallet.

        The execution ledger only knows about transactions the fund runtime has
        registered. The explorer address history is the authoritative view for
        this screen because the same signing wallet can also send a transaction
        through another client. Token transfers are joined to the wallet's
        outgoing transactions and converted into the same normalized shape used
        by the existing execution cards.
        """

        wallet = wallet_address.strip()
        if not _is_address(wallet):
            return []
        cache_key = wallet.lower()
        now = time.monotonic()
        cached = self._wallet_history_cache.get(cache_key)
        cache_seconds = max(0.0, float(os.getenv("BLOCKSCOUT_WALLET_HISTORY_CACHE_SECONDS", "30")))
        if cached is not None and now - cached[0] < cache_seconds:
            return [dict(item) for item in cached[1]]

        try:
            transactions = self._paged_items(f"/api/v2/addresses/{wallet}/transactions")
            transfers = self._paged_items(f"/api/v2/addresses/{wallet}/token-transfers")
        except Exception:
            # The rest of the portfolio remains usable when the optional public
            # indexer is unavailable. A later request retries after the cache
            # window rather than turning the websocket request into an error.
            return [dict(item) for item in cached[1]] if cached is not None else []

        transfers_by_hash: dict[str, list[Mapping[str, Any]]] = {}
        for transfer in transfers:
            tx_hash = str(transfer.get("transaction_hash") or transfer.get("transactionHash") or "").lower()
            if tx_hash:
                transfers_by_hash.setdefault(tx_hash, []).append(transfer)

        result: list[dict[str, Any]] = []
        wallet_key = wallet.lower()
        for transaction in transactions:
            if not isinstance(transaction, Mapping):
                continue
            tx_hash = str(transaction.get("hash") or transaction.get("transaction_hash") or "")
            if not _is_tx_hash(tx_hash):
                continue
            sender = _nested_hash(transaction.get("from"))
            if sender.lower() != wallet_key:
                continue
            tx_transfers = transfers_by_hash.get(tx_hash.lower(), [])
            sent = [item for item in tx_transfers if _nested_hash(item.get("from")).lower() == wallet_key]
            received = [item for item in tx_transfers if _nested_hash(item.get("to")).lower() == wallet_key]
            if not sent and not received:
                continue
            timestamp_ms = _timestamp_ms(transaction.get("timestamp"))
            status = _explorer_status(transaction.get("status"))
            base = {
                "txHash": tx_hash,
                "chainId": chain_id,
                "status": status,
                "explorerUrl": explorer_url(tx_hash),
                "timestampMs": timestamp_ms,
                "blockNumber": _as_int(transaction.get("block_number")),
                "transactionIndex": _as_int(transaction.get("transaction_index")),
                "sender": sender,
                "recipient": _nested_hash(transaction.get("to")) or None,
                "transactionFee": _nested_value(transaction.get("fee")),
                "flyIds": [],
            }

            # One swap can have both legs. Emit one normalized row per leg so
            # the buy list and sell list each contain that transaction.
            for transfer in sent:
                token = _token_details(transfer)
                if token is None:
                    continue
                counterpart = _first_transfer_amount(received)
                result.append({
                    **base,
                    "executionId": f"wallet:{tx_hash}:sell:{token['address'].lower()}",
                    "biologicalEventId": f"wallet:{tx_hash}",
                    "side": "sell",
                    "tokenSymbol": token["symbol"],
                    "tokenAddress": token["address"],
                    "inputToken": token["address"],
                    "inputAmount": token["amount"],
                    "actualInputAmount": token["amount"],
                    "expectedOutput": counterpart,
                    "actualOutputAmount": counterpart,
                })
            for transfer in received:
                token = _token_details(transfer)
                if token is None:
                    continue
                input_transfer = _first_transfer_amount(sent)
                native_value = _native_value(transaction.get("value"))
                result.append({
                    **base,
                    "executionId": f"wallet:{tx_hash}:buy:{token['address'].lower()}",
                    "biologicalEventId": f"wallet:{tx_hash}",
                    "side": "buy",
                    "tokenSymbol": token["symbol"],
                    "tokenAddress": token["address"],
                    "inputToken": input_transfer["address"] if input_transfer else _zero_address(),
                    "inputAmount": input_transfer["amount"] if input_transfer else native_value,
                    "actualInputAmount": input_transfer["amount"] if input_transfer else native_value,
                    "expectedOutput": token["amount"],
                    "actualOutputAmount": token["amount"],
                })

        # Newest first, stable across pages and across the two explorer feeds.
        result.sort(key=lambda item: (int(item.get("timestampMs") or 0), str(item.get("txHash") or "")), reverse=True)
        self._wallet_history_cache[cache_key] = (now, result)
        return [dict(item) for item in result]

    def _paged_items(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_params: Mapping[str, Any] | None = None
        while True:
            query = f"?{urlencode({str(key): str(value) for key, value in next_params.items()})}" if next_params else ""
            url = f"{self.base_url.rstrip('/')}{path}{query}"
            payload = self.fetcher(url, self.timeout_seconds) if self.fetcher else self._request(url)
            if not isinstance(payload, Mapping):
                raise RuntimeError("Blockscout returned a non-object page")
            page_items = payload.get("items")
            if isinstance(page_items, list):
                items.extend(item for item in page_items if isinstance(item, dict))
            raw_next = payload.get("next_page_params")
            if not isinstance(raw_next, Mapping) or not raw_next:
                return items
            next_params = raw_next

    def _request(self, url: str) -> Any:
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "fruit-fly-capital/0.1"}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(str(exc)) from exc


@dataclass(frozen=True)
class ReceiptObservation:
    status: str
    explorer_url: str
    block_number: int | None = None
    transaction_index: int | None = None
    sender: str | None = None
    recipient: str | None = None
    gas_used: str | None = None
    effective_gas_price: str | None = None
    transaction_fee: str | None = None
    receipt_status: str | None = None
    actual_input_amount: str | None = None
    actual_output_amount: str | None = None
    actual_token_received: dict[str, Any] | None = None
    transfer_events: tuple[dict[str, Any], ...] = ()
    blockscout: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "explorerUrl": self.explorer_url,
            "blockNumber": self.block_number,
            "transactionIndex": self.transaction_index,
            "from": self.sender,
            "to": self.recipient,
            "gasUsed": self.gas_used,
            "effectiveGasPrice": self.effective_gas_price,
            "transactionFee": self.transaction_fee,
            "receiptStatus": self.receipt_status,
            "actualInputAmount": self.actual_input_amount,
            "actualOutputAmount": self.actual_output_amount,
            "actualTokenReceived": self.actual_token_received,
            "transferEvents": list(self.transfer_events),
            "blockscout": self.blockscout,
            "error": self.error,
        }


def explorer_url(tx_hash: str) -> str:
    base_url = os.getenv("FUND_EXPLORER_URL", ROBINHOOD_EXPLORER_URL).strip() or ROBINHOOD_EXPLORER_URL
    return f"{base_url.rstrip('/')}/tx/{tx_hash}"


def observe_receipt(
    wallet: Any,
    tx_hash: str,
    *,
    side: str,
    token_address: str,
    token_symbol: str,
    input_token: str,
    input_amount: str,
    blockscout: BlockscoutClient | None = None,
    wallet_before_native_wei: int | None = None,
    wallet_before_input_raw: int | None = None,
    wallet_before_output_raw: int | None = None,
    output_decimals: int | None = None,
) -> ReceiptObservation:
    """Read one canonical receipt and derive best-effort transfer amounts."""

    url = explorer_url(tx_hash)
    receipt = wallet.call("eth_getTransactionReceipt", [tx_hash])
    if receipt is None:
        return ReceiptObservation(ReceiptStatus.PENDING, url)
    raw_receipt_status = receipt.get("status")
    if raw_receipt_status is None:
        return ReceiptObservation(ReceiptStatus.PENDING, url)
    receipt_status = _hex_int(raw_receipt_status)
    if receipt_status == 0:
        status = ReceiptStatus.REVERTED
    elif receipt_status == 1:
        status = ReceiptStatus.CONFIRMED
    else:
        return ReceiptObservation(ReceiptStatus.PENDING, url, receipt_status=_hex_or_none(receipt.get("status")))

    transaction = wallet.call("eth_getTransactionByHash", [tx_hash]) or {}
    sender = _address_from_topic(transaction.get("from")) or _address_from_topic(receipt.get("from"))
    recipient = _address_from_topic(transaction.get("to")) or _address_from_topic(receipt.get("to"))
    gas_used_int = _hex_int(receipt.get("gasUsed"))
    effective_price_int = _hex_int(receipt.get("effectiveGasPrice"))
    fee_int = gas_used_int * effective_price_int
    transfers = _transfer_events(receipt.get("logs"), sender)
    token_key = token_address.lower()
    relevant = [event for event in transfers if str(event.get("tokenAddress", "")).lower() == token_key]
    wallet_key = str(getattr(wallet, "wallet_address", "")).lower()
    if not wallet_key and sender:
        wallet_key = sender.lower()
    token_sent_raw = sum(int(event["amountRaw"]) for event in relevant if str(event.get("from", "")).lower() == wallet_key)
    token_received_raw = sum(int(event["amountRaw"]) for event in relevant if str(event.get("to", "")).lower() == wallet_key)

    tx_value = _hex_int(transaction.get("value"))
    actual_input = _format_raw(token_sent_raw if input_token.lower() != _zero_address() else tx_value, 18)
    if side.lower() == "buy":
        actual_output = _format_raw(token_received_raw, output_decimals or 0) if token_received_raw else None
        received = {"tokenAddress": token_address, "tokenSymbol": token_symbol, "amountRaw": str(token_received_raw), "amount": actual_output, "decimals": output_decimals} if token_received_raw else None
    else:
        actual_output = _native_output_after_fee(wallet, wallet_before_native_wei, fee_int)
        received = {"tokenAddress": _zero_address(), "tokenSymbol": "ETH", "amount": actual_output, "amountRaw": _raw_from_decimal(actual_output, 18) if actual_output is not None else None, "decimals": 18} if actual_output is not None else None
    metadata: dict[str, Any] | None = None
    metadata_error: str | None = None
    if status == ReceiptStatus.CONFIRMED and blockscout is not None:
        try:
            metadata = blockscout.transaction(tx_hash)
        except Exception as exc:
            # Public enrichment is optional. Never turn this into an on-chain
            # failure or alter the canonical receipt classification.
            metadata_error = str(exc)
    return ReceiptObservation(
        status=status,
        explorer_url=url,
        block_number=_hex_int_or_none(receipt.get("blockNumber")),
        transaction_index=_hex_int_or_none(receipt.get("transactionIndex")),
        sender=sender,
        recipient=recipient,
        gas_used=str(gas_used_int),
        effective_gas_price=str(effective_price_int),
        transaction_fee=str(fee_int),
        receipt_status=_hex_or_none(receipt.get("status")),
        actual_input_amount=actual_input,
        actual_output_amount=actual_output,
        actual_token_received=received,
        transfer_events=tuple(relevant),
        blockscout=metadata,
        error=metadata_error,
    )


def _transfer_events(logs: Any, wallet_address: str | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(logs, list):
        return result
    for log in logs:
        if not isinstance(log, Mapping):
            continue
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
            continue
        amount_raw = _hex_int(log.get("data"))
        result.append({
            "tokenAddress": str(log.get("address") or ""),
            "from": _address_from_topic(topics[1]),
            "to": _address_from_topic(topics[2]),
            "amountRaw": str(amount_raw),
            "walletInvolved": bool(wallet_address and wallet_address.lower() in {str(_address_from_topic(topics[1]) or "").lower(), str(_address_from_topic(topics[2]) or "").lower()}),
        })
    return result


def _native_output_after_fee(wallet: Any, before_wei: int | None, fee_wei: int) -> str | None:
    if before_wei is None:
        return None
    try:
        after_wei = int(wallet.snapshot().native_balance_wei)
    except Exception:
        return None
    output_wei = after_wei - before_wei + fee_wei
    return _format_raw(output_wei, 18) if output_wei >= 0 else None


def _format_raw(value: int, decimals: int) -> str:
    if decimals <= 0:
        return str(value)
    return format(Decimal(value) / (Decimal(10) ** decimals), "f")


def _raw_from_decimal(value: str | None, decimals: int) -> str | None:
    if value is None:
        return None
    try:
        return str(int(Decimal(value) * (Decimal(10) ** decimals)))
    except Exception:
        return None


def _hex_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(str(value), 16) if str(value).startswith("0x") else int(str(value))


def _hex_int_or_none(value: Any) -> int | None:
    return None if value is None else _hex_int(value)


def _hex_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _address_from_topic(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    raw = value[2:]
    if len(raw) == 64:
        raw = raw[-40:]
    return f"0x{raw}" if len(raw) == 40 else None


def _zero_address() -> str:
    return "0x0000000000000000000000000000000000000000"


def _is_address(value: str) -> bool:
    return bool(len(value) == 42 and value.startswith("0x") and all(character in "0123456789abcdefABCDEF" for character in value[2:]))


def _is_tx_hash(value: str) -> bool:
    return bool(len(value) == 66 and value.startswith("0x") and all(character in "0123456789abcdefABCDEF" for character in value[2:]))


def _nested_hash(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("hash") or value.get("address_hash")
    return str(value or "")


def _nested_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("value")
    return str(value) if value is not None else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return None


def _explorer_status(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"ok", "success", "confirmed"}:
        return ReceiptStatus.CONFIRMED
    if normalized in {"pending", "awaiting"}:
        return ReceiptStatus.PENDING
    return ReceiptStatus.REVERTED


def _token_details(transfer: Mapping[str, Any]) -> dict[str, str] | None:
    token = transfer.get("token")
    total = transfer.get("total")
    if not isinstance(token, Mapping) or not isinstance(total, Mapping):
        return None
    address = str(token.get("address_hash") or token.get("address") or "")
    if not _is_address(address):
        return None
    raw = str(total.get("value") or "0")
    try:
        amount = _format_raw(int(raw), int(total.get("decimals") or token.get("decimals") or 0))
    except (TypeError, ValueError):
        amount = raw
    symbol = str(token.get("symbol") or token.get("name") or f"{address[:8]}…")
    return {"address": address, "symbol": symbol, "amount": amount}


def _first_transfer_amount(transfers: list[Mapping[str, Any]]) -> dict[str, str] | None:
    for transfer in transfers:
        details = _token_details(transfer)
        if details is not None:
            return details
    return None


def _native_value(value: Any) -> str:
    try:
        if value is None:
            return "0"
        raw = int(str(value), 16) if str(value).startswith("0x") else int(str(value))
        return _format_raw(raw, 18)
    except (TypeError, ValueError):
        return "0"
