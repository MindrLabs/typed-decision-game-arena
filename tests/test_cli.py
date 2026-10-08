from __future__ import annotations

from pathlib import Path

import pytest

from arena.cli import main


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "macro: Macro." in out
    assert "kev-0.8b" in out and "reference" in out


def test_show_prints_the_question(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "--board", "macro", "--game", "snake", "--seed", "1001"]) == 0
    out = capsys.readouterr().out
    assert "Snake on a 10 x 10 grid" in out
    assert "[straight] go straight" in out


def test_show_adds_the_real_time_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "--board", "realtime", "--game", "tetris"]) == 0
    assert "Real time: the game does not wait for you" in capsys.readouterr().out


def test_the_frozen_suite_matches_the_tree(capsys: pytest.CaptureFixture[str]) -> None:
    # suite v0.1 is frozen: a change to a locked source or package belongs in a new suite version
    assert main(["suite", "check"]) == 0, capsys.readouterr().out


def test_run_score_and_verify_into_a_results_directory(tmp_path: Path) -> None:
    results = str(tmp_path / "results")
    common = ["--board", "macro", "--game", "snake", "--seeds", "1001-1002", "--seed-set", "dev"]
    for player in ("random", "reference"):
        assert main(["run", *common, "--player", player, "--results", results]) == 0
    assert main(["verify", "--seed-set", "dev", "--results", results]) == 0
    assert main(["score", "--seed-set", "dev", "--results", results]) == 0
    assert (tmp_path / "results" / "v0.1" / "scores-dev.json").exists()


def test_explicit_seeds_must_belong_to_the_seed_set() -> None:
    with pytest.raises(SystemExit, match="not dev seeds"):
        main(
            ["run", "--board", "macro", "--game", "snake", "--player", "random", "--seeds", "1-2", "--seed-set", "dev"]
        )
