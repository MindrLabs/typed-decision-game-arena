"""Where results live and how they are written.

    results/<suite>/<seed set>/<board>/<game>/<player>/episodes.jsonl        one line per finished episode
    results/<suite>/<seed set>/<board>/<game>/<player>/decisions/<seed>.jsonl.gz   every decision, then the end
    results/<suite>/<seed set>/<board>/<game>/<player>/errors.jsonl          episodes that failed (re-run later)
    results/<suite>/latency/<player>.json                                    latency measurements

A decision file is written under a temporary name and renamed when its episode finishes, and the episode line is
appended only after that, so an interrupted run never leaves a half episode that looks complete.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from arena.core import JSON
from arena.episode import DecisionRecord
from arena.suite import ROOT

RESULTS = ROOT / "results"


def say(line: str) -> None:
    """A progress line, on stderr and flushed at once, so that a log under systemd follows a run live."""
    print(line, file=sys.stderr, flush=True)


def run_dir(suite_id: str, seed_set: str, board: str, game: str, player: str, *, results: Path = RESULTS) -> Path:
    return results / suite_id / seed_set / board / game / player


def episodes_path(directory: Path) -> Path:
    return directory / "episodes.jsonl"


def decisions_path(directory: Path, seed: int) -> Path:
    return directory / "decisions" / f"{seed}.jsonl.gz"


def decision_json(record: DecisionRecord) -> JSON:
    q, d = record.question, record.decision
    return {
        "i": record.index,
        "step": record.step,
        "snapshot": record.snapshot,
        "state": q.state,
        "instructions": q.instructions,
        "options": [{"key": o.key, "text": o.text} for o in q.options],
        "calls": [call.to_json() for call in d.calls],
        "choice": d.choice,
        "forced": d.forced,
    }


class DecisionWriter:
    """Gzipped JSONL of one episode's decisions, published atomically by `commit`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.temporary = path.with_name(path.name + ".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Held open across `write` calls and closed by `commit` or `discard`, so no `with` block.
        self._file: gzip.GzipFile | None = gzip.GzipFile(self.temporary, "wb", compresslevel=6)

    def write(self, record: DecisionRecord) -> None:
        assert self._file is not None
        line = json.dumps(decision_json(record), separators=(",", ":"), ensure_ascii=False)
        self._file.write(line.encode() + b"\n")

    def finish(self, snapshot: JSON, step: int) -> None:
        """The last line: the position after the final move (a topped-out well, the winning four)."""
        assert self._file is not None
        line = json.dumps(
            {"final": True, "step": step, "snapshot": snapshot}, separators=(",", ":"), ensure_ascii=False
        )
        self._file.write(line.encode() + b"\n")

    def commit(self) -> None:
        assert self._file is not None
        self._file.close()
        self._file = None
        os.replace(self.temporary, self.path)

    def discard(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self.temporary.unlink(missing_ok=True)


def append_jsonl(path: Path, item: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[JSON]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _log_lines(path: Path) -> Iterator[JSON]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def read_decisions(path: Path) -> Iterator[JSON]:
    """The decision lines of an episode log (without the closing `final` line)."""
    for item in _log_lines(path):
        if not item.get("final"):
            yield item


def read_final(path: Path) -> JSON | None:
    """The closing line of an episode log: {"final": true, "step": ..., "snapshot": ...}."""
    last = None
    for item in _log_lines(path):
        if item.get("final"):
            last = item
    return last


def read_episodes(directory: Path) -> list[JSON]:
    """Episode lines, the last one per seed winning (a re-run after a fix replaces the earlier line)."""
    by_seed: dict[int, JSON] = {}
    for item in read_jsonl(episodes_path(directory)):
        by_seed[int(item["seed"])] = item
    return [by_seed[seed] for seed in sorted(by_seed)]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
