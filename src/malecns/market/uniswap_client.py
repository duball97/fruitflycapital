"""Uniswap Trading API boundary.

This client can request a quote and unsigned calldata. It intentionally has
no private key, signer, wallet, or broadcast method.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


class UniswapApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class TradeIntent:
    habitat_id: str
    side: str
    token_in: str
    token_out: str
    amount: str
    chain_id: int
    rationale: str
    status: str = "proposal_only"
    requires_human_signature: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "habitatId": self.habitat_id,
            "side": self.side,
            "tokenIn": self.token_in,
            "tokenOut": self.token_out,
            "amount": self.amount,
            "chainId": self.chain_id,
            "rationale": self.rationale,
            "status": self.status,
            "requiresHumanSignature": self.requires_human_signature,
        }


@dataclass(frozen=True)
class UniswapTradingClient:
    api_key: str
    base_url: str = "https://trade-api.gateway.uniswap.org/v1"
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "UniswapTradingClient | None":
        api_key = os.getenv("UNISWAP_API_KEY", "").strip()
        return cls(api_key=api_key) if api_key else None

    def quote(self, request_body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/quote", request_body)

    def check_approval(self, request_body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/check_approval", request_body)

    def create_unsigned_swap(self, quote: dict[str, Any], *, permit_data: dict[str, Any] | None = None, deadline: int | None = None) -> dict[str, Any]:
        # Trading API /swap consumes the quote response fields at the top
        # level; wrapping them under {"quote": ...} is not the documented
        # request shape.
        body: dict[str, Any] = dict(quote)
        if permit_data is not None:
            body["permitData"] = permit_data
        if deadline is not None:
            body["deadline"] = deadline
        return self._post("/swap", body)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                # Robinhood Chain mainnet is supported by Universal Router
                # 2.1.1; it has no 2.0 deployment.
                "x-universal-router-version": os.getenv("UNISWAP_ROUTER_VERSION", "2.1.1"),
                # The current fund boundary always requires a human review;
                # it is not an autonomous transaction agent.
                "x-agent-info": '{"integration_name":"swap-integration","decision_origin":"human_mediated","version":"1.5.0"}',
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise UniswapApiError(f"Uniswap API request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise UniswapApiError("Uniswap API returned a non-object response")
        return payload
