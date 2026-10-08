"""The campaign end to end on a tiny suite behind the stand-in server: order, resumption, failures, waiting."""

from __future__ import annotations

from pathlib import Path

import pytest

from arena.campaign import (
    Campaign,
    GpuBusyError,
    ServerUnavailableError,
    format_status,
    status,
    wait_for_quiet_gpu,
    wait_for_server,
)
from arena.core import PlayerError
from arena.gpu import GpuProcess
from arena.logs import read_jsonl, run_dir
from arena.suite import Suite
from tests.fakes import FakeModelCompose


def campaign(suite: Suite, results: Path, server: str, lines: list[str], *, attempts: int = 3) -> Campaign:
    return Campaign(
        suite,
        "dev",
        server=server,
        results=results,
        anchor_workers=1,
        attempts=attempts,
        latency_sample=2,
        bias_sample=2,
        say=lines.append,
        processes=lambda: [],
    )


def files(results: Path) -> dict[Path, int]:
    return {p: p.stat().st_mtime_ns for p in results.rglob("*") if p.is_file()}


def test_a_campaign_runs_everything_once(tiny: Suite, results: Path, server: str) -> None:
    lines: list[str] = []
    assert campaign(tiny, results, server, lines).run(["kev-0.8b"]).failed == []
    rows = {row.player: row for row in status(tiny, "dev", results)}
    assert rows["kev-0.8b"].boards == {"macro": (2, 2), "frame": (2, 2), "realtime": (2, 2)}
    assert rows["kev-0.8b"].latency and rows["kev-0.8b"].bias
    assert rows["reference"].boards == {"macro": (2, 2), "frame": (2, 2), "realtime": None}
    assert rows["laya-english"].boards["macro"] == (0, 2) and rows["laya-english"].latency is False

    # anchors first, then the model: its turn-based boards, latency, the real-time board, bias
    def first(prefix: str) -> int:
        return next(i for i, line in enumerate(lines) if line.startswith(prefix))

    steps = [
        first("== anchors"),
        first("== kev-0.8b"),
        first("macro/snake kev-0.8b"),
        first("frame/tetris kev-0.8b"),
        first("kev-0.8b macro/snake: median"),
        first("realtime/tetris kev-0.8b"),
        first("kev-0.8b snake: "),
    ]
    assert steps == sorted(steps)

    before = files(results)
    lines.clear()
    assert campaign(tiny, results, server, lines).run(["kev-0.8b"]).failed == []
    assert files(results) == before  # nothing measured or played twice
    assert lines[-1] == "campaign complete"


def test_a_model_that_is_not_served_does_not_hold_up_the_others(tiny: Suite, results: Path, server: str) -> None:
    FakeModelCompose.served = ["kev-0.8b"]
    report = campaign(tiny, results, server, []).run(["laya-english", "kev-0.8b"], anchors=False)
    (failure,) = report.failed
    assert failure.startswith("laya-english: laya-english is not served")
    rows = {row.player: row for row in status(tiny, "dev", results)}
    assert rows["kev-0.8b"].boards["realtime"] == (2, 2)


def test_failing_steps_are_retried_then_reported(
    tiny: Suite, results: Path, server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("arena.client.time.sleep", lambda seconds: None)
    FakeModelCompose.fail_after = 2  # the two smoke questions pass, every later request fails
    report = campaign(tiny, results, server, [], attempts=2).run(["kev-0.8b"], anchors=False)
    assert report.failed[:2] == [
        "macro/snake kev-0.8b: 2 episodes still fail",
        "frame/tetris kev-0.8b: 2 episodes still fail",
    ]
    assert report.failed[2].startswith("latency kev-0.8b: kev-0.8b: no answer after 3 attempts")
    assert report.failed[3] == "realtime kev-0.8b: skipped, no latency"
    assert report.failed[4].startswith("bias kev-0.8b:")
    errors = read_jsonl(run_dir(tiny.id, "dev", "macro", "snake", "kev-0.8b", results=results) / "errors.jsonl")
    assert len(errors) == 4  # two seeds, two attempts

    FakeModelCompose.fail_after = None  # the next run picks up what is left
    assert campaign(tiny, results, server, []).run(["kev-0.8b"], anchors=False).failed == []


def test_a_model_that_cannot_answer_is_skipped_at_once(
    tiny: Suite, results: Path, server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("arena.client.time.sleep", lambda seconds: None)
    FakeModelCompose.fail = True
    (failure,) = campaign(tiny, results, server, []).run(["kev-0.8b"], anchors=False).failed
    assert failure.startswith("kev-0.8b: no answer on macro/snake, skipped:")
    assert not (run_dir(tiny.id, "dev", "macro", "snake", "kev-0.8b", results=results) / "errors.jsonl").exists()


def test_unknown_models_are_refused_before_anything_runs(tiny: Suite, results: Path, server: str) -> None:
    with pytest.raises(KeyError, match="unknown models"):
        campaign(tiny, results, server, []).run(["random"])
    assert not results.exists()


def test_waiting_for_the_server(server: str) -> None:
    lines: list[str] = []
    wait_for_server(server, "kev-0.8b", 0, say=lines.append)
    assert lines == []
    with pytest.raises(PlayerError, match="kev-99b is not served"):
        wait_for_server(server, "kev-99b", 0, say=lines.append)
    clock = iter(range(100))
    with pytest.raises(ServerUnavailableError, match="no model server"):
        wait_for_server(
            "http://127.0.0.1:9/api", "kev-0.8b", 3, say=lines.append, sleep=lambda s: None, clock=lambda: next(clock)
        )
    assert lines == ["waiting for the model server at http://127.0.0.1:9/api (ConnectError)"]


def test_latency_waits_for_other_models_to_leave_the_gpu() -> None:
    loaded = GpuProcess(11, "/srv/arena/.runtime/clef/bin/python", 56_000)
    idle = GpuProcess(11, "/srv/arena/.runtime/clef/bin/python", 399)
    own = GpuProcess(12, "/srv/arena/.runtime/kev-9b/bin/python", 18_000)
    seen = iter([[loaded, own], [loaded, own], [idle, own]])
    lines: list[str] = []
    sleeps: list[float] = []
    wait_for_quiet_gpu("kev-9b", 60, say=lines.append, processes=lambda: next(seen), sleep=sleeps.append)
    assert sleeps == [10.0, 10.0]
    assert lines == ["latency of kev-9b waits for the GPU: runtime clef (56000 MiB)"]

    clock = iter(range(0, 1000, 10))
    with pytest.raises(GpuBusyError, match="stayed busy"):
        wait_for_quiet_gpu(
            "kev-9b", 30, say=lines.append, processes=lambda: [loaded], sleep=lambda s: None, clock=lambda: next(clock)
        )


def test_status_table(tiny: Suite, results: Path) -> None:
    table = format_status(status(tiny, "dev", results)).splitlines()
    assert table[0].split() == ["player", "macro", "frame", "realtime", "latency", "bias"]
    assert table[1].split() == ["random", "0/2", "0/2", "-", "-", "-"]
    assert table[3].split()[1:] == ["0/2", "0/2", "0/2", "no", "no"]
