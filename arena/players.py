"""Players: typed-decision models served by model-compose, and the two anchors every score is scaled by.

* `random`: a uniformly random legal option (the 0 of every normalised score).
* `reference`: a strong rule-based player per game that reads the structured view, never the text (the 100).
"""

from __future__ import annotations

import time

from arena import families, protocol
from arena.client import ModelClient
from arena.core import Call, Decision, DecisionPoint, PlayerError, Question
from arena.games import breakout, connect4, pong, snake, tetris
from arena.registry import Contestant
from arena.seeding import Rng


class TextPlayer:
    """A typed-decision model behind a model-compose workflow."""

    def __init__(self, contestant: Contestant, client: ModelClient, group_size: int) -> None:
        self.contestant = contestant
        self.id = contestant.id
        self.client = client
        self.group_size = group_size

    def start(self, seed: int) -> None:
        pass

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        return protocol.decide(point.question, self.ask, rng, self.group_size)

    def ask(self, question: Question, stage: str) -> Call:
        payload = families.payload(self.contestant.family, question)
        started = time.perf_counter()
        output = self.client.run(self.id, payload)
        latency = (time.perf_counter() - started) * 1000
        try:
            choice, probabilities = families.parse(output, question.keys)
        except families.ResponseError as error:
            raise PlayerError(f"{self.id}: {error}") from error
        return Call(stage, question.keys, choice, probabilities, latency)

    def close(self) -> None:
        self.client.close()


class RandomPlayer:
    id = "random"

    def start(self, seed: int) -> None:
        pass

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        return Decision(rng.choice(point.question.keys))

    def close(self) -> None:
        pass


class ReferencePlayer:
    """The strongest simple player we know for each game; documented next to each game engine."""

    id = "reference"

    def __init__(self, game: str, track: str, settings: dict[str, int] | None = None) -> None:
        self.game = game
        self.track = track
        self.settings = settings or {}
        self._planner = tetris.FramePlanner()

    def start(self, seed: int) -> None:
        self._planner.start()

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        view = point.view
        match self.game, self.track:
            case "tetris", "macro":
                key = tetris.reference_macro(view)
            case "tetris", "frame":
                key = self._planner(view)
            case "snake", _:
                key = snake.reference_move(view.game)
            case "connect4", _:
                key = connect4.reference_move(view, int(self.settings.get("depth", 7)), rng)
            case "pong", "macro":
                key = pong.reference_macro(view)
            case "pong", "frame":
                key = pong.reference_frame(view)
            case "breakout", "macro":
                key = breakout.reference_macro(view)
            case "breakout", "frame":
                key = breakout.reference_frame(view)
            case _:
                raise KeyError(f"no reference player for {self.game}/{self.track}")
        return Decision(key)

    def close(self) -> None:
        pass
