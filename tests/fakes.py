"""A stand-in for model-compose's HTTP API, enough for the runner and the diagnostics."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


class FakeModelCompose(BaseHTTPRequestHandler):
    """Answers every typed-decision request with the first option shown (both question shapes)."""

    fail = False

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
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
