"""Build the task for a (board, game) pair of a suite."""

from __future__ import annotations

from arena.core import Task
from arena.games import breakout, connect4, pong, snake, tetris
from arena.suite import Suite


def make_task(suite: Suite, board: str, game: str) -> Task:
    """A fresh task; unknown parameters in the suite file fail here rather than being ignored."""
    spec = suite.game(board, game)
    params = dict(spec.params)
    match spec.track, game:
        case "macro", "tetris":
            return tetris.TetrisMacro(**params)
        case "frame", "tetris":
            return tetris.TetrisFrame(**params)
        case "macro", "snake":
            return snake.SnakeTask(**params)
        case "macro", "connect4":
            return connect4.Connect4Task(**params)
        case "macro", "pong":
            return pong.PongMacro(**params, sticky=suite.sticky)
        case "frame", "pong":
            return pong.PongFrame(**params, sticky=suite.sticky)
        case "macro", "breakout":
            return breakout.BreakoutMacro(**params, sticky=suite.sticky)
        case "frame", "breakout":
            return breakout.BreakoutFrame(**params, sticky=suite.sticky)
    raise KeyError(f"no task for track {spec.track!r} and game {game!r}")
