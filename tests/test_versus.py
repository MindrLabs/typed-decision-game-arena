"""Versus site data (arena/versus.py): run comparison against the shared golden cases, and the export shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arena import versus
from arena.core import JSON
from arena.runner import run
from arena.suite import Suite

GOLDEN = Path(__file__).parent / "golden" / "versus-series.json"


def quiet(line: str) -> None:
    pass


def _series(raw: JSON) -> versus.Series:
    return versus.Series(tuple((int(p), float(s)) for p, s in raw["points"]), int(raw["end"]), float(raw["final"]))


@pytest.mark.parametrize("case", json.loads(GOLDEN.read_text())["cases"], ids=lambda c: c["name"])
def test_compare_matches_the_golden_cases(case: JSON) -> None:
    result = versus.compare(_series(case["a"]), _series(case["b"]))
    assert result.lead_changes == case["lead_changes"]
    assert result.chase is case["chase"]
    assert result.margin == case["margin"]


def test_series_counts_a_finished_run_with_its_final_score() -> None:
    s = _series({"points": [[0, 0], [3, 1]], "end": 5, "final": 2})
    assert [s.at(p) for p in (0, 2, 3, 4, 5, 9)] == [0, 0, 1, 1, 2, 2]


def test_series_from_a_decision_log_by_decision_and_by_step() -> None:
    decisions = [
        {"i": 0, "step": 0, "snapshot": {"eaten": 0}},
        {"i": 1, "step": 4, "snapshot": {"eaten": 1}},
    ]
    final = {"step": 9, "snapshot": {"eaten": 2}}
    by_decision = versus.series("snake", decisions, final, "decision")
    assert by_decision.points == ((0, 0.0), (1, 1.0))
    assert by_decision.end == 2
    by_step = versus.series("snake", decisions, final, "step")
    assert by_step.points == ((0, 0.0), (4, 1.0))
    assert by_step.end == 9


def test_versus_data_from_two_players(tiny: Suite, results: Path) -> None:
    for player in ("random", "reference"):
        run(tiny, "macro", "snake", player, [1, 2], seed_set="dev", results=results, progress=quiet)
    data = versus.versus_data(tiny, "dev", ["random", "reference"], results=results)
    assert [g["board"] + "/" + g["game"] for g in data["games"]] == ["macro/snake"]
    episodes = data["episodes"]["macro/snake"]
    assert set(episodes) == {"random", "reference"}
    assert set(episodes["random"]) == {"1", "2"}
    score, length, end = episodes["reference"]["1"]
    assert isinstance(length, int)
    assert end
    rows = data["matches"]["macro/snake"]["random~reference"]
    assert set(rows) == {"1", "2"}
    assert data["par"]["macro/snake"]["1"] == score
    assert len(data["picks"]) == 2
    assert data["duel"] is None or isinstance(data["duel"], dict)
