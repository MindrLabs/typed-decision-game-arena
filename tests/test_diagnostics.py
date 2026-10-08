"""Latency, position bias, site export and the environment record, against the stand-in server."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from arena import bias, latency
from arena.environment import describe
from arena.export import export
from arena.logs import read_json, write_json
from arena.probe import sample_questions
from arena.runner import run
from arena.score import StaleResultsError
from arena.suite import Suite, locked_digest


def quiet(line: str) -> None:
    pass


def test_probe_questions_are_fixed_and_fit_one_request(suite: Suite) -> None:
    first = sample_questions(suite, "macro", "tetris", 5)
    again = sample_questions(suite, "macro", "tetris", 5)
    assert [q.to_json() for q in first] == [q.to_json() for q in again]
    assert all(2 <= len(q.options) <= suite.group_size for q in first)


def test_latency_file(suite: Suite, results: Path, server: str) -> None:
    path = latency.measure(suite, "kev-0.8b", server=server, sample=3, warmup=1, results=results, progress=quiet)
    data = read_json(path)
    assert set(data["games"]) == {f"{b}/{g}" for b, g in suite.pairs() if b != "realtime"}
    assert all(entry["n"] == 3 and entry["median_ms"] > 0 for entry in data["games"].values())
    assert data["lock"] == locked_digest(suite)
    assert isinstance(data["environment"]["gpu_processes_at_start"], list)


def test_a_position_follower_shows_up_in_the_bias_report(suite: Suite, results: Path, server: str) -> None:
    # the stand-in server always picks the first option shown
    path = bias.measure(suite, "kev-0.8b", server=server, sample=8, results=results, progress=quiet)
    overall = read_json(path)["overall"]
    assert overall["first_rate"] == 1.0
    assert overall["agreement"] == 0.0
    assert overall["uniform_rate"] < 0.5


def test_export_writes_index_and_replays(suite: Suite, results: Path, tmp_path: Path) -> None:
    for player in ("random", "reference"):
        run(suite, "macro", "snake", player, [1001], seed_set="dev", results=results, progress=quiet)
    out = tmp_path / "data"
    index_path = export(suite, "dev", out=out, results=results, replays_per_player=1)
    index = json.loads(index_path.read_text())
    assert index["schema"] == 1
    assert index["seed_set"] == "dev"
    assert {b["id"] for b in index["boards"]} == {"macro", "frame", "realtime"}
    assert {"random", "reference", "kev-0.8b"} <= set(index["players"])
    (replay,) = [r for r in index["replays"] if r["player"] == "reference"]
    data = json.loads(gzip.decompress((out / replay["path"]).read_bytes()))
    assert data["game"] == "snake" and data["decisions"][0]["i"] == 0
    first = (out / replay["path"]).read_bytes()
    export(suite, "dev", out=out, results=results, replays_per_player=1)
    assert (out / replay["path"]).read_bytes() == first  # byte-identical archives


def test_environment_record() -> None:
    record = describe()
    assert record["model_compose"] and len(record["model_compose"]) == 40
    assert record["python"].startswith("3.12")


def test_a_test_export_refuses_diagnostics_from_another_lock(frozen: Suite, results: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    out.mkdir()
    (out / "index.json").write_text("{}")
    write_json(bias.bias_path(frozen.id, "kev-0.8b", results), {"lock": None, "games": {}, "overall": {"n": 0}})
    with pytest.raises(StaleResultsError, match="another suite lock"):
        export(frozen, "test", out=out, results=results)
    assert (out / "index.json").read_text() == "{}"  # a refused export leaves the old data in place
