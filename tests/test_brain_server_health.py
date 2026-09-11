from __future__ import annotations

import asyncio
from http import HTTPStatus
from types import SimpleNamespace

from malecns.brain_server import RuntimeRegistry, process_http_request


class _Connection:
    def respond(self, status: HTTPStatus, text: str) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=status,
            body=text,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )


def _request(path: str, *, upgrade: str = "") -> SimpleNamespace:
    return SimpleNamespace(path=path, headers={"Upgrade": upgrade})


def test_health_endpoint_returns_json_for_render_probe() -> None:
    response = process_http_request(_Connection(), _request("/healthz?probe=1"))

    assert response is not None
    assert response.status_code == HTTPStatus.OK
    assert '"status": "ok"' in response.body
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store"


def test_root_health_does_not_intercept_websocket_upgrade() -> None:
    assert process_http_request(_Connection(), _request("/", upgrade="websocket")) is None


def test_unknown_http_path_returns_not_found() -> None:
    response = process_http_request(_Connection(), _request("/missing"))

    assert response is not None
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_runtime_registry_falls_back_after_memory_safe_cap() -> None:
    created: list[int] = []

    def factory(*_args: object, seed: int, **_kwargs: object) -> object:
        created.append(seed)
        return SimpleNamespace(manifest={"path_hops": 3})

    registry = RuntimeRegistry(
        "unused",
        max_live_runtimes=2,
        runtime_factory=factory,  # type: ignore[arg-type]
    )

    async def load() -> tuple[object | None, object | None, object | None]:
        return (
            await registry.get("fly-001"),
            await registry.get("fly-002"),
            await registry.get("fly-003"),
        )

    first, second, overflow = asyncio.run(load())

    assert first is not None
    assert second is not None
    assert overflow is None
    assert len(created) == 2
