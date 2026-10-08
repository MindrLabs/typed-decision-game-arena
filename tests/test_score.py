from __future__ import annotations

from pathlib import Path

import pytest

from arena.logs import append_jsonl, episodes_path, run_dir
from arena.score import StaleResultsError, holm, score, score_board
from arena.suite import Suite


def write(results: Path, suite: Suite, board: str, game: str, player: str, *, scores: dict[int, float]) -> None:
    directory = run_dir(suite.id, "dev", board, game, player, results=results)
    for seed, value in scores.items():
        append_jsonl(
            episodes_path(directory),
            {"seed": seed, "score": value, "metrics": {"won": value > 0}, "decisions": 1, "latency_ms": None},
        )


def fill(results: Path, suite: Suite, player: str, fraction: float, jitter: float = 0.0) -> None:
    """Scores at `fraction` of the way from random (0) to reference (10) on every macro game."""
    for game, spec in suite.board("macro").games.items():
        seeds = spec.seeds["dev"]
        write(results, suite, "macro", game, "random", scores=dict.fromkeys(seeds, 0.0))
        write(results, suite, "macro", game, "reference", scores=dict.fromkeys(seeds, 10.0))
        write(
            results,
            suite,
            "macro",
            game,
            player,
            scores={s: 10 * fraction + jitter * (i % 2) for i, s in enumerate(seeds)},
        )


def test_normalised_index(suite: Suite, results: Path) -> None:
    fill(results, suite, "kev-0.8b", 0.5)
    board = score_board(suite, "dev", "macro", results)
    info = board["players"]["kev-0.8b"]
    assert info["index"] == 50.0
    assert info["index_ci"] == [50.0, 50.0]  # identical scores on every seed
    assert board["players"]["random"]["index"] == 0.0
    assert board["players"]["reference"]["index"] == 100.0
    assert board["ranking"] == ["reference", "kev-0.8b", "random"]


def test_scores_are_clipped_to_the_anchors(suite: Suite, results: Path) -> None:
    fill(results, suite, "kev-4b", 1.5)
    assert score_board(suite, "dev", "macro", results)["players"]["kev-4b"]["index"] == 100.0


def test_report_is_reproducible_and_pairwise(suite: Suite, results: Path) -> None:
    fill(results, suite, "kev-0.8b", 0.4, jitter=2.0)
    fill(results, suite, "kev-4b", 0.6, jitter=2.0)
    first, second = score(suite, "dev", results), score(suite, "dev", results)
    assert first == second
    (pair,) = first["boards"]["macro"]["pairs"]
    assert pair["a"] == "kev-4b"
    assert pair["diff"] == pytest.approx(20.0)
    assert 0.0 < pair["p_holm"] <= 1.0


def test_incomplete_players_are_not_ranked(suite: Suite, results: Path) -> None:
    fill(results, suite, "kev-0.8b", 0.5)
    write(results, suite, "macro", "tetris", "kev-9b", scores={1001: 3.0})
    board = score_board(suite, "dev", "macro", results)
    assert "kev-9b" not in board["ranking"]
    assert board["players"]["kev-9b"]["complete"] is False


def test_holm() -> None:
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([]) == []


def test_test_results_must_match_the_current_lock(suite: Suite, results: Path) -> None:
    directory = run_dir(suite.id, "test", "macro", "snake", "kev-0.8b", results=results)
    append_jsonl(episodes_path(directory), {"seed": 1, "score": 3.0, "lock": "an-older-lock", "metrics": {}})
    with pytest.raises(StaleResultsError, match="another suite lock"):
        score_board(suite, "test", "macro", results)
