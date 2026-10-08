"""HTTP client for model-compose workflows (`POST {base}/workflows/runs`)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from arena.core import PlayerError

DEFAULT_SERVER = "http://127.0.0.1:8380/api"


class ServerError(RuntimeError):
    """The server answered but the workflow did not complete."""


class ModelClient:
    def __init__(
        self,
        base_url: str = DEFAULT_SERVER,
        *,
        timeout: float = 900.0,
        retries: int = 2,
        backoff: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.backoff = backoff
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def run(self, workflow_id: str, payload: dict[str, Any]) -> Any:
        """Run a workflow to completion and return its output. Transport errors, 5xx responses and failed runs
        are retried; after `retries` retries the last error is raised as `PlayerError`."""
        body = {"workflow_id": workflow_id, "input": payload, "wait_for_completion": True}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._http.post("/workflows/runs", json=body)
                if response.status_code == 404:
                    raise PlayerError(f"workflow {workflow_id!r} is not served at {self.base_url}")
                response.raise_for_status()
                result = response.json()
                if result.get("status") != "completed":
                    raise ServerError(f"workflow {workflow_id} {result.get('status')}: {result.get('error')}")
                return result.get("output")
            except (httpx.TransportError, httpx.HTTPStatusError, ServerError, ValueError) as error:
                last = error
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise PlayerError(f"{workflow_id}: no answer after {self.retries + 1} attempts: {last}") from last

    def workflows(self) -> list[str]:
        response = self._http.get("/workflows")
        response.raise_for_status()
        items = response.json()
        return [str(item.get("workflow_id") or item.get("id")) for item in items]

    def close(self) -> None:
        self._http.close()
