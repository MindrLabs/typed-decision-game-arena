"""Replay verification: feed every logged choice back into a fresh game and demand the same game.

For each decision the replay compares, byte for byte, the state text, instructions, options and snapshot the
engine produces now with what was logged, then plays the logged choice. At the end the score must match the
episode line. Any engine, renderer or protocol drift since the run shows up as the first differing decision.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from arena.core import JSON, Decision, DecisionPoint
from arena.episode import DecisionRecord, play
from arena.logs import RESULTS, decisions_path, read_decisions, read_episodes, read_final, run_dir
from arena.seeding import Rng
from arena.suite import Suite
from arena.tasks import make_task


class ReplayMismatchError(AssertionError):
    pass


@dataclass(frozen=True)
class Verified:
    board: str
    game: str
    player: str
    seed: int
    decisions: int
    problem: str | None


def _normalised(value: object) -> object:
    return json.loads(json.dumps(value))


class _LoggedPlayer:
    def __init__(self, player_id: str, log: list[JSON]) -> None:
        self.id = player_id
        self.log = log
        self.position = 0

    def start(self, seed: int) -> None:
        pass

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        if self.position >= len(self.log):
            raise ReplayMismatchError(f"the game asks decision {self.position}, the log ends at {len(self.log)}")
        return Decision(self.log[self.position]["choice"])

    def close(self) -> None:
        pass


def verify_episode(suite: Suite, seed_set: str, episode: JSON, results: Path = RESULTS) -> int:
    """Replays one episode; returns the number of decisions checked or raises `ReplayMismatchError`."""
    board, game, player, seed = episode["board"], episode["game"], episode["player"], int(episode["seed"])
    directory = run_dir(suite.id, seed_set, board, game, player, results=results)
    log = list(read_decisions(decisions_path(directory, seed)))
    task = make_task(suite, board, game)
    logged = _LoggedPlayer(player, log)

    def check(record: DecisionRecord) -> None:
        i = logged.position
        if i >= len(log):
            raise ReplayMismatchError(f"decision {i} is not in the log ({len(log)} logged)")
        entry = log[i]
        q = record.question
        produced = {
            "state": q.state,
            "instructions": q.instructions,
            "options": [{"key": o.key, "text": o.text} for o in q.options],
            "snapshot": _normalised(record.snapshot),
            "forced": record.decision.forced,
            "step": record.step,
        }
        for name, value in produced.items():
            if entry[name] != value:
                raise ReplayMismatchError(
                    f"decision {i}: {name} differs\n  logged:   {entry[name]!r:.400}\n  now:      {value!r:.400}"
                )
        logged.position += 1

    try:
        outcome = play(
            task,
            logged,
            seed,
            suite_id=suite.id,
            board=board,
            delay_steps=int(episode["delay_steps"]),
            on_decision=check,
        )
        final = read_final(decisions_path(directory, seed))
        if final is None:
            raise ReplayMismatchError("the log has no final line")
        if final["snapshot"] != _normalised(task.snapshot()) or final["step"] != task.steps:
            raise ReplayMismatchError("the final position differs from the logged one")
    finally:
        task.close()
    if logged.position != len(log):
        raise ReplayMismatchError(f"the game ended after {logged.position} decisions, the log has {len(log)}")
    if outcome.score != episode["score"]:
        raise ReplayMismatchError(f"score {outcome.score} differs from the logged {episode['score']}")
    return len(log)


def verify(
    suite: Suite,
    seed_set: str,
    *,
    boards: list[str] | None = None,
    games: list[str] | None = None,
    players: list[str] | None = None,
    results: Path = RESULTS,
) -> Iterator[Verified]:
    base = results / suite.id / seed_set
    for board, game in suite.pairs():
        if (boards and board not in boards) or (games and game not in games):
            continue
        game_dir = base / board / game
        if not game_dir.exists():
            continue
        for player_dir in sorted(p for p in game_dir.iterdir() if p.is_dir()):
            if players and player_dir.name not in players:
                continue
            for episode in read_episodes(player_dir):
                try:
                    count = verify_episode(suite, seed_set, episode, results)
                    yield Verified(board, game, player_dir.name, int(episode["seed"]), count, None)
                except (ReplayMismatchError, FileNotFoundError) as error:
                    yield Verified(board, game, player_dir.name, int(episode["seed"]), 0, str(error))
