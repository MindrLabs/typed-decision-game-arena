"""A stand-in for model-compose's HTTP API, enough for the runner and the diagnostics."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from arena.registry import contestants


class FakeModelCompose(BaseHTTPRequestHandler):
    """Answers every typed-decision request with the first option shown (both question shapes)."""

    fail = False
    served: list[str] | None = None  # workflows it serves; None: every player in model-compose.yml

    def _served(self) -> list[str]:
        return list(contestants()) if self.served is None else self.served

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/workflows"):
            self._send(200, [{"workflow_id": w, "title": w} for w in self._served()])
        else:
            self._send(404, {"detail": "Not Found"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["workflow_id"] not in self._served():
            self._send(404, {"detail": f"Workflow not found: {body['workflow_id']}"})
            return
        if self.fail:
            self._send(200, {"status": "failed", "error": "boom"})
            return
        move = body["input"]["schema"]["move"]
        keys = move["choices"] if move["type"] == "enum" else list(move["criteria"])
        scores = {k: (0.7 if i == 0 else 0.3 / (len(keys) - 1)) for i, k in enumerate(keys)}
        self._send(
            200,
            {"status": "completed", "output": {"decision": {"move": keys[0]}, "fields": {"move": {"scores": scores}}}},
        )

    def _send(self, code: int, payload: object) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass
