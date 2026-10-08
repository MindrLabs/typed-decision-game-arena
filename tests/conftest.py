from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from arena.suite import SUITES, Suite, load_suite
from tests.fakes import FakeModelCompose

# A suite small enough to run every step of a campaign in seconds: one game per turn-based board, short caps.
TINY = """
id = "t0"
group_size = 8
bootstrap = 20
confidence = 0.95

[atari]
sticky = 0.25

[boards.macro]
title = "Macro"
summary = "Turn-based."
order = 1

[boards.macro.games.snake]
step_cap = 40
starve_cap = 30
seeds = { dev = "1-2", test = "11-12" }

[boards.frame]
title = "Frame"
summary = "Turn-based, one step per decision."
order = 2

[boards.frame.games.tetris]
piece_cap = 2
gravity = 2
seeds = { dev = "1-2", test = "11-12" }

[boards.realtime]
title = "Real-time"
summary = "The frame board with reaction time."
order = 3
from = "frame"
step_ms = 66.6667
"""


@pytest.fixture(scope="session")
def suite() -> Suite:
    return load_suite("v0.1")


@pytest.fixture
def frozen(tmp_path: Path) -> Suite:
    """Suite v0.1 in a temporary directory, with a stand-in lock file (its digest is what the checks compare)."""
    directory = tmp_path / "suites"
    directory.mkdir()
    shutil.copy(SUITES / "v0.1.toml", directory / "v0.1.toml")
    (directory / "v0.1.lock.json").write_text('{"stand-in": "lock"}\n')
    return load_suite("v0.1", directory)


@pytest.fixture
def tiny(tmp_path: Path) -> Suite:
    directory = tmp_path / "suites"
    directory.mkdir(exist_ok=True)
    (directory / "t0.toml").write_text(TINY)
    return load_suite("t0", directory)


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
    FakeModelCompose.served = None
