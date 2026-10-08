from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from arena.suite import LOCKED_SOURCES, ROOT, Suite, freeze, load_suite, lock_differences, parse_seeds
from arena.tasks import make_task


def test_suite_shape(suite: Suite) -> None:
    assert [b.id for b in sorted(suite.boards.values(), key=lambda b: b.order)] == ["macro", "frame", "realtime"]
    assert set(suite.board("macro").games) == {"tetris", "snake", "connect4", "pong", "breakout"}
    assert set(suite.board("frame").games) == {"tetris", "pong", "breakout"}
    realtime = suite.board("realtime")
    assert realtime.based_on == "frame"
    assert realtime.step_ms == pytest.approx(66.6667)
    assert realtime.games["pong"].params == suite.game("frame", "pong").params
    assert suite.game("realtime", "tetris").track == "frame"


def test_seed_sets_are_disjoint(suite: Suite) -> None:
    for board, game in suite.pairs():
        seeds = suite.game(board, game).seeds
        assert not set(seeds["dev"]) & set(seeds["test"])


def test_parse_seeds() -> None:
    assert parse_seeds("1-3,7, 9-10") == [1, 2, 3, 7, 9, 10]
    with pytest.raises(ValueError, match="repeats"):
        parse_seeds("1-3,2")
    with pytest.raises(ValueError, match="empty"):
        parse_seeds("5-1")


def test_every_pair_builds_a_task(suite: Suite) -> None:
    for board, game in suite.pairs():
        task = make_task(suite, board, game)
        assert task.game == game
        task.close()


def copy_tree(tmp: Path) -> Path:
    for name in LOCKED_SOURCES:
        target = tmp / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, target)
    (tmp / "suites").mkdir()
    shutil.copy(ROOT / "suites" / "v0.1.toml", tmp / "suites" / "v0.1.toml")
    return tmp


def test_freeze_then_detect_changes(tmp_path: Path) -> None:
    root = copy_tree(tmp_path)
    suite = load_suite("v0.1", root / "suites")
    assert lock_differences(suite, root) == ["v0.1.lock.json does not exist (the suite is not frozen yet)"]
    freeze(suite, root)
    assert lock_differences(suite, root) == []
    with pytest.raises(FileExistsError):
        freeze(suite, root)
    tetris = root / "arena" / "games" / "tetris.py"
    tetris.write_text(tetris.read_text() + "\n# changed\n")
    (problem,) = lock_differences(suite, root)
    assert problem.startswith("sources: arena/games/tetris.py")
