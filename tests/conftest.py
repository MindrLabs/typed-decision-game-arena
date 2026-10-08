from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from arena.suite import Suite, load_suite
from tests.fakes import FakeModelCompose


@pytest.fixture(scope="session")
def suite() -> Suite:
    return load_suite("v0.1")


@pytest.fixture
def results(tmp_path: Path) -> Path:
    return tmp_path / "results"


@pytest.fixture
def server() -> Iterator[str]:
    """A stand-in model-compose server on a free port (see tests/fakes.py)."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeModelCompose)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api"
    httpd.shutdown()
    FakeModelCompose.fail = False
