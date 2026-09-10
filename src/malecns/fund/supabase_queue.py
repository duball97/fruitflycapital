"""Server-only Supabase REST queue for cross-service execution intents."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class SupabaseQueueError(RuntimeError):
    pass


class SupabaseIntentQueue:
    def __init__(self, url: str, key: str, table: str = "execution_intents") -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.table = table

    @classmethod
    def from_env(cls) -> "SupabaseIntentQueue | None":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            return None
        return cls(url, key, os.getenv("SUPABASE_INTENT_TABLE", "execution_intents").strip() or "execution_intents")

    def _request(self, method: str, path: str, body: Any = None, query: str = "", prefer: str | None = None) -> Any:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = Request(f"{self.url}/rest/v1/{path}{query}", headers=headers, data=json.dumps(body).encode() if body is not None else None, method=method)
        try:
            with urlopen(request, timeout=float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "8"))) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SupabaseQueueError(f"Supabase queue HTTP {exc.code}: {detail[:500]}") from exc
        except Exception as exc:
            raise SupabaseQueueError(f"Supabase queue request failed: {exc}") from exc

    def enqueue(self, payload: Mapping[str, Any]) -> bool:
        intent = payload.get("executionIntent")
        token = payload.get("token")
        if not isinstance(intent, Mapping) or not isinstance(token, Mapping):
            raise SupabaseQueueError("queue payload must contain executionIntent and token")
        row = {
            "idempotency_key": intent["idempotencyKey"],
            "side": intent["side"],
            "chain_id": int(intent["chainId"]),
            "token_in": intent["tokenIn"],
            "token_out": intent["tokenOut"],
            "amount_in": str(intent["amountIn"]),
            "fly_ids": list(intent.get("flyIds") or []),
            "biological_event_id": intent.get("biologicalEventId"),
            "payload": dict(payload),
        }
        self._request("POST", self.table, [row], prefer="resolution=ignore-duplicates,return=minimal")
        return True

    def claim(self, worker_id: str, limit: int = 1) -> list[dict[str, Any]]:
        rows = self._request("POST", "rpc/claim_execution_intents", {"p_worker_id": worker_id, "p_limit": limit, "p_lease_seconds": int(os.getenv("FUND_QUEUE_LEASE_SECONDS", "120"))})
        return [dict(row) for row in rows] if isinstance(rows, list) else []

    def finish(self, key: str, status: str, result: Mapping[str, Any] | None = None, error: str | None = None) -> None:
        query = f"?idempotency_key=eq.{key}"
        body = {"status": status, "result": dict(result) if result is not None else None, "error": error, "lease_until": None, "updated_at": "now()"}
        # PostgREST cannot evaluate now() in a JSON PATCH, so omit it; the
        # database timestamp remains accurate enough for queue recovery.
        body.pop("updated_at")
        self._request("PATCH", self.table, body, query=query, prefer="return=minimal")

    @staticmethod
    def new_worker_id() -> str:
        return f"render-worker-{uuid.uuid4().hex[:12]}"
