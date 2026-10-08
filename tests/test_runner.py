"""Runs end to end: baselines, a model behind a fake model-compose server, resumption, failures, replay checks."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from arena.core import JSON
from arena.logs import decisions_path, read_decisions, read_episodes, read_final, read_jsonl, run_dir, write_json
from arena.replay import verify
from arena.runner import LatencyMissingError, SuiteNotFrozenError, delay_steps, latency_path, run
from arena.suite import Suite, locked_digest
from tests.fakes import FakeModelCompose


def quiet(line: str) -> None:
    pass


def test_baselines_run_resume_and_replay(suite: Suite, results: Path) -> None:
    summary = run(suite, "macro", "snake", "reference", [1001, 1002], seed_set="dev", results=results, progress=quiet)
    assert len(summary.finished) == 2
    again = run(suite, "macro", "snake", "reference", [1001, 1002], seed_set="dev", results=results, progress=quiet)
    assert again.skipped == 2
    assert not again.finished
    checked = list(verify(suite, "dev", results=results))
    assert [v.problem for v in checked] == [None, None]


def test_parallel_workers_play_the_same_episodes(suite: Suite, tmp_path: Path) -> None:
    # workers are spawned processes: the job, suite included, has to pickle, and play must not depend on the process
    seeds = [1001, 1002, 1003]
    serial = run(suite, "macro", "connect4", "random", seeds, seed_set="dev", results=tmp_path / "a", progress=quiet)
    parallel = run(
        suite, "macro", "connect4", "random", seeds, seed_set="dev", workers=2, results=tmp_path / "b", progress=quiet
    )

    def outcome(episodes: list[JSON]) -> list[tuple[object, ...]]:
        return sorted((e["seed"], e["score"], e["decisions"], e["steps"]) for e in episodes)

    assert outcome(serial.finished) == outcome(parallel.finished)
    assert len(parallel.finished) == len(seeds)


def test_replay_catches_a_tampered_log(suite: Suite, results: Path) -> None:
    run(suite, "macro", "connect4", "random", [1001], seed_set="dev", results=results, progress=quiet)
    path = decisions_path(run_dir(suite.id, "dev", "macro", "connect4", "random", results=results), 1001)
    lines = gzip.decompress(path.read_bytes()).decode().splitlines()
    first = json.loads(lines[0])
    first["state"] = first["state"].replace("Move", "Turn")
    lines[0] = json.dumps(first)
    path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode()))
    (item,) = verify(suite, "dev", results=results)
    assert item.problem is not None
    assert "decision 0: state differs" in item.problem


def test_test_seeds_need_a_frozen_suite(suite: Suite, results: Path) -> None:
    with pytest.raises(SuiteNotFrozenError):
        run(suite, "macro", "snake", "random", [1], seed_set="test", results=results, progress=quiet)


def test_a_model_through_http(suite: Suite, results: Path, server: str) -> None:
    summary = run(
        suite, "macro", "tetris", "kev-0.8b", [1001], seed_set="dev", server=server, results=results, progress=quiet
    )
    (episode,) = summary.finished
    assert episode["calls"] > episode["decisions"]  # T, J and L pieces go through the knockout
    assert episode["latency_ms"]["n"] == episode["calls"]
    assert episode["model"]["revision"] == "bf75a6a8848ea6960ff2ed108d9ed44c2941174f"
    assert len(episode["model"]["config_sha"]) == 64
    assert [v.problem for v in verify(suite, "dev", results=results)] == [None]


def test_nimble_requests_take_the_enum_shape(suite: Suite, results: Path, server: str) -> None:
    summary = run(
        suite, "macro", "snake", "nimble", [1001], seed_set="dev", server=server, results=results, progress=quiet
    )
    assert summary.finished and not summary.failed


def test_a_failing_server_is_recorded_not_fatal(suite: Suite, results: Path, server: str) -> None:
    FakeModelCompose.fail = True
    summary = run(
        suite, "macro", "snake", "kev-0.8b", [1001], seed_set="dev", server=server, results=results, progress=quiet
    )
    assert not summary.finished
    directory = run_dir(suite.id, "dev", "macro", "snake", "kev-0.8b", results=results)
    (error,) = read_jsonl(directory / "errors.jsonl")
    assert "boom" in error["error"]
    assert not read_episodes(directory)
    assert not list((directory / "decisions").glob("*"))  # no half-written decision log


def test_real_time_delay_comes_from_measured_latency(suite: Suite, results: Path) -> None:
    assert delay_steps(suite, "frame", "pong", "kev-0.8b", results) == 0
    with pytest.raises(LatencyMissingError):
        delay_steps(suite, "realtime", "pong", "kev-0.8b", results)
    write_json(latency_path(suite.id, "kev-0.8b", results), {"games": {"frame/pong": {"median_ms": 150.0}}})
    assert delay_steps(suite, "realtime", "pong", "kev-0.8b", results) == 3  # ceil(150 / 66.67)
    write_json(latency_path(suite.id, "kev-0.8b", results), {"games": {"frame/pong": {"median_ms": 12.0}}})
    assert delay_steps(suite, "realtime", "pong", "kev-0.8b", results) == 1  # never below one step
    with pytest.raises(ValueError, match="anchors are the frame board"):
        delay_steps(suite, "realtime", "pong", "reference", results)


def test_test_seeds_take_only_a_latency_measured_under_the_current_lock(frozen: Suite, results: Path) -> None:
    path = latency_path(frozen.id, "kev-0.8b", results)
    write_json(path, {"lock": None, "games": {"frame/pong": {"median_ms": 150.0}}})
    assert delay_steps(frozen, "realtime", "pong", "kev-0.8b", results) == 3  # dev seeds take any measurement
    with pytest.raises(LatencyMissingError, match="another suite lock"):
        delay_steps(frozen, "realtime", "pong", "kev-0.8b", results, seed_set="test")
    write_json(path, {"lock": locked_digest(frozen), "games": {"frame/pong": {"median_ms": 150.0}}})
    assert delay_steps(frozen, "realtime", "pong", "kev-0.8b", results, seed_set="test") == 3


def test_an_unknown_player_is_refused_before_any_episode(suite: Suite, results: Path) -> None:
    with pytest.raises(KeyError, match="unknown player"):
        run(suite, "macro", "snake", "kev-99b", [1001], seed_set="dev", results=results, progress=quiet)
    assert not results.exists()


def test_logs_end_with_the_final_position(suite: Suite, results: Path) -> None:
    run(suite, "macro", "connect4", "reference", [1001], seed_set="dev", results=results, progress=quiet)
    path = decisions_path(run_dir(suite.id, "dev", "macro", "connect4", "reference", results=results), 1001)
    final = read_final(path)
    assert final is not None and final["snapshot"]["result"] in {"win", "loss", "draw"}
    assert all("final" not in item for item in read_decisions(path))

    lines = gzip.decompress(path.read_bytes()).decode().splitlines()
    tampered = json.loads(lines[-1])
    tampered["snapshot"]["result"] = "draw" if tampered["snapshot"]["result"] != "draw" else "win"
    lines[-1] = json.dumps(tampered)
    path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode()))
    (item,) = verify(suite, "dev", results=results)
    assert item.problem == "the final position differs from the logged one"
