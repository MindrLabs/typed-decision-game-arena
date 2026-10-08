"""The RAM readings and the controllers of the ALE games, checked against the emulator's own screen."""

from __future__ import annotations

import numpy as np
import pytest

from arena.games import breakout as B
from arena.games import pong as P
from arena.games.atari import Motion, motion, reflect
from arena.seeding import Rng

pytestmark = pytest.mark.ale

WHITE = np.array((236, 236, 236))
GREEN = np.array((92, 186, 92))
RED = np.array((200, 72, 72))


def boxes(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def test_pong_ram_matches_the_screen() -> None:
    game = P.Pong(sticky=0.0)
    game.reset(0)
    rng = Rng(1)
    checked = 0
    for _ in range(400):
        game.step(rng.choice([P.UP, P.DOWN, P.NOOP]))
        screen = game.screen()
        field = screen[34:194]
        paddle = boxes(np.all(field[:, 140:144] == GREEN, axis=2))
        if paddle is not None and paddle[2] > 2 and paddle[3] < 157:  # fully inside the field
            place = P.span(game.player_top())
            assert place is not None
            assert abs(paddle[2] - place[0]) <= 1 and abs(paddle[3] - place[1]) <= 1
        ball = game.ball()
        found = boxes(np.all(field == WHITE, axis=2))
        if ball is not None and found is not None:
            assert abs(found[0] - ball[0]) <= 1 and abs(found[2] - ball[1]) <= 1
            checked += 1
    assert checked > 100


def test_pong_actions_move_the_paddle_the_documented_way() -> None:
    game = P.Pong(sticky=0.0)
    game.reset(0)
    for _ in range(6):
        game.step(P.DOWN)
    low = game.player_top()
    for _ in range(4):
        game.step(P.UP)
    assert game.player_top() < low


def test_breakout_ram_matches_the_screen() -> None:
    game = B.Breakout(sticky=0.0)
    game.reset(0)
    rng = Rng(2)
    checked = 0
    for _ in range(300):
        if game.ball() is None:
            game.step(B.FIRE)
            continue
        game.step(rng.choice([B.LEFT, B.RIGHT, B.NOOP]))
        left, right = game.paddle_span()
        assert right - left + 1 in (8, 16)  # full or shrunk paddle
        assert abs(left - game.paddle_left()) <= 1
        ball = game.ball()
        screen = game.screen()
        found = boxes(np.all(screen[100:185, 8:152] == RED, axis=2))  # below the bricks, above the paddle
        if ball is not None and found is not None and 70 < ball[1] < 150:
            assert abs(found[0] - ball[0]) <= 1 and abs(found[2] + 100 - (ball[1] + 32)) <= 1
            checked += 1
    assert checked > 20


def test_breakout_reads_the_bricks() -> None:
    game = B.Breakout(sticky=0.0)
    game.reset(0)
    assert game.bricks() == ["#" * 18] * 6


def test_same_seed_and_actions_replay_exactly() -> None:
    def trajectory(seed: int, sticky: float) -> list[bytes]:
        game = P.Pong(sticky=sticky)
        game.reset(seed)
        rng = Rng(5)
        out = []
        for _ in range(300):
            game.step(rng.choice([P.UP, P.DOWN, P.NOOP]))
            out.append(bytes(game.ram))
        game.close()
        return out

    assert trajectory(1, 0.25) == trajectory(1, 0.25)
    assert trajectory(1, 0.25) != trajectory(2, 0.25)  # sticky actions make seeds differ
    assert trajectory(1, 0.0) == trajectory(2, 0.0)  # without them the console is deterministic


def test_motion_waits_for_three_consistent_steps() -> None:
    # moving right and up, bouncing off the top wall between the 3rd and 4th position
    positions: list[tuple[int, int] | None] = [(80, 9), (84, 1), (88, 3), (92, 11)]
    m = motion(positions)
    assert m == Motion(92, 11, 4, 8, 1)  # the bounce leaves only the last step usable
    m = motion([*positions[1:], (96, 19)])
    assert m == Motion(96, 19, 8, 16, 2)  # three steps agree: two-step window
    assert motion([None, (1, 1)]) is None


def test_reflect_folds_into_the_field() -> None:
    assert reflect(5, 0, 10) == 5
    assert reflect(12, 0, 10) == 8
    assert reflect(-3, 0, 10) == 3
    assert reflect(25, 0, 10) == 5


def test_pong_macro_reference_beats_random() -> None:
    def play(seed: int, reference: bool) -> float:
        task = P.PongMacro()
        task.reset(seed)
        rng = Rng(seed)
        while not task.done:
            point = task.decision_point()
            task.apply(P.reference_macro(point.view) if reference else rng.choice(point.question.keys))
        task.close()
        return task.score()

    assert play(1, True) - play(1, False) >= 5


def test_breakout_frame_reference_beats_random() -> None:
    def play(seed: int, reference: bool) -> float:
        task = B.BreakoutFrame(step_cap=600)
        task.reset(seed)
        rng = Rng(seed)
        while not task.done:
            point = task.decision_point()
            task.apply(B.reference_frame(point.view) if reference else rng.choice(point.question.keys))
        task.close()
        return task.score()

    assert play(1, True) > play(1, False) + 10


def test_pong_says_what_is_missing_before_the_first_serve() -> None:
    task = P.PongFrame()
    task.reset(1001)
    first = task.decision_point().question.state
    # the console leaves a half-set ball and an opponent paddle above the field in RAM at the start
    assert "No ball is in play." in first
    assert "The opponent's paddle is not on the field." in first
    assert "--" not in first and "x -" not in first
    assert task.snapshot()["opponent"] is None
    for _ in range(20):
        task.apply("stay")
    later = task.decision_point().question.state
    assert "The opponent's paddle covers y " in later
    task.close()


def test_breakout_frame_ends_when_no_ball_is_launched() -> None:
    task = B.BreakoutFrame(idle_cap=40)
    task.reset(1001)
    assert "the game ends unless one is launched within 40 steps" in task.decision_point().question.state
    while not task.done:
        task.apply("stay")
    assert task.steps == 40
    assert task.metrics()["idle_end"] is True
    task.close()

    task = B.BreakoutFrame(step_cap=400, idle_cap=40)  # the reference launches at once and never runs into it
    task.reset(1001)
    while not task.done:
        task.apply(B.reference_frame(task.decision_point().view))
    assert task.steps == 400 and task.metrics()["idle_end"] is False
    task.close()
