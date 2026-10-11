"""Direct games (arena/duel.py): openings, a full run against the fake model server, replay checks and ratings."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from arena import duel
from arena.core import JSON, Decision, DecisionPoint
from arena.games.connect4 import COLS
from arena.seeding import Rng
from arena.suite import LOCKED_SOURCES, load_suite, manifest
from tests.fakes import FakeModelCompose


def quiet(line: str) -> None:
    pass


class First:
    """Plays the leftmost legal column."""

    def __init__(self, player_id: str) -> None:
        self.id = player_id

    def start(self, seed: int) -> None:
        pass

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        return Decision(point.question.keys[0])

    def close(self) -> None:
        pass


def test_openings_are_the_25_up_to_mirror_image() -> None:
    assert len(duel.OPENINGS) == 25
    mirrored = {(COLS - 1 - x, COLS - 1 - o) for x, o in duel.OPENINGS}
    assert len(set(duel.OPENINGS) | mirrored) == 49
    assert len({duel.opening(seed) for seed in range(1, 26)}) == 25
    assert duel.opening(26) == duel.opening(1)


def test_pairs_and_colours() -> None:
    assert duel.pair_id("nimble", "clef") == "clef~nimble"
    assert duel.x_player("clef~nimble", 1) == "clef"
    assert duel.x_player("clef~nimble", 2) == "nimble"
    with pytest.raises(ValueError, match="two different"):
        duel.pair_id("clef", "clef")
    assert duel.schedule(["a", "b", "c"]) == ["a~b", "a~c", "b~c"]


def test_a_game_starts_after_the_opening_and_asks_the_side_to_move() -> None:
    task = duel.Connect4Duel()
    task.reset(1)
    assert task.board.history == list(duel.opening(1))
    point = task.decision_point()
    assert task.side == 0
    assert "You play X" in point.question.state
    task.apply(point.question.keys[0])
    assert "You play O" in task.decision_point().question.state


def test_play_duel_alternates_and_finishes() -> None:
    records: list[tuple[int, int]] = []
    task = duel.Connect4Duel()
    outcome = duel.play_duel(
        task,
        (First("a"), First("b")),
        3,
        1,
        suite_id="duel-v0.1",
        on_decision=lambda side, item: records.append((side, item.index)),
    )
    assert outcome.result in ("X", "O", "draw")
    assert [side for side, _ in records] == [i % 2 for i in range(len(records))]
    assert outcome.moves == 2 + len(records)
    assert sum(outcome.decisions) == len(records)


def test_duel_suite_locks_the_duel_module_and_v01_does_not() -> None:
    duel_suite = load_suite("duel-v0.1")
    assert duel_suite.kind == "duel"
    assert "arena/duel.py" in manifest(duel_suite)["sources"]
    single = load_suite("v0.1")
    assert single.kind == "single"
    assert set(manifest(single)["sources"]) == set(LOCKED_SOURCES)


def test_run_resume_verify_and_score(server: str, results: Path) -> None:
    suite = load_suite("duel-v0.1")
    pairs = ["kev-0.8b~laya-typed"]
    summary = duel.run_duels(suite, "dev", pairs, server=server, results=results, room=None, progress=quiet)
    assert len(summary.finished) == 4  # two dev seeds, two games each
    assert not summary.failed
    again = duel.run_duels(suite, "dev", pairs, server=server, results=results, room=None, progress=quiet)
    assert again.skipped == 4
    assert not again.finished

    game = summary.finished[0]
    assert game["x"] == "kev-0.8b"
    assert game["o"] == "laya-typed"
    assert sum(game["points"].values()) == 1.0
    assert set(game["latency_ms"]) == {"kev-0.8b", "laya-typed"}

    checked = list(duel.verify(suite, "dev", results=results))
    assert [v.problem for v in checked] == [None] * 4

    report = duel.score(suite, "dev", results=results, replicates=20)
    assert report["games"] == 4
    assert set(report["ratings"]) == {"kev-0.8b", "laya-typed"}
    assert report["pairs"]["kev-0.8b~laya-typed"]["games"] == 4


def test_verify_catches_a_changed_choice(server: str, results: Path) -> None:
    suite = load_suite("duel-v0.1")
    duel.run_duels(suite, "dev", ["kev-0.8b~laya-typed"], seeds=[21], server=server, results=results, room=None)
    path = duel.decisions_file(duel.pair_dir(suite.id, "dev", "kev-0.8b~laya-typed", results=results), 21, 1)
    with gzip.open(path, "rt") as handle:
        lines = [json.loads(line) for line in handle]
    first = lines[0]
    other = next(o["key"] for o in first["options"] if o["key"] != first["choice"])
    first["choice"] = other
    path.write_bytes(gzip.compress("".join(json.dumps(line) + "\n" for line in lines).encode()))
    problems = [v.problem for v in duel.verify(suite, "dev", results=results) if v.problem]
    assert problems


def test_failed_games_are_logged_and_run_again(server: str, results: Path) -> None:
    suite = load_suite("duel-v0.1")
    FakeModelCompose.fail = True
    summary = duel.run_duels(
        suite, "dev", ["kev-0.8b~laya-typed"], seeds=[21], server=server, results=results, room=None
    )
    assert len(summary.failed) == 2
    FakeModelCompose.fail = False
    retry = duel.run_duels(suite, "dev", ["kev-0.8b~laya-typed"], seeds=[21], server=server, results=results, room=None)
    assert len(retry.finished) == 2


def _game(x: str, o: str, result: str, seed: int = 1) -> JSON:
    points = {"X": {x: 1.0, o: 0.0}, "O": {x: 0.0, o: 1.0}, "draw": {x: 0.5, o: 0.5}}[result]
    return {"x": x, "o": o, "points": points, "seed": seed}


def test_bradley_terry_orders_by_results() -> None:
    games = [_game("a", "b", "X", s) for s in range(5)] + [_game("b", "c", "X", s) for s in range(5)]
    strength = duel._bradley_terry(["a", "b", "c"], games)
    assert strength["a"] > strength["b"] > strength["c"]
    level = duel._bradley_terry(["a", "b"], [_game("a", "b", "draw"), _game("b", "a", "draw")])
    assert level["a"] == pytest.approx(level["b"])
    assert duel.elo(1.0) == 1500.0
