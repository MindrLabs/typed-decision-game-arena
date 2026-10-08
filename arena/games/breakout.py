"""Atari Breakout (ALE `Breakout-v5`).

Field coordinates: x 0-143 between the side walls, y 0 just under the top wall; the paddle's top edge is at y 157.
Bricks fill six rows of eighteen (y 25-60), worth 7, 7, 4, 4, 1 and 1 points from the top row down. The paddle
is 16 pixels wide (it can shrink during the game; the state reports its current span); the ball is 2 x 4 pixels.

* `macro`: a decision whenever the ball starts falling or rising, or bounces off a side wall while falling (each
  time once three consistent steps show the new direction). The player picks one of 8 vertical bands, 18 pixels
  each, and a fixed controller moves the paddle centre to the middle of that band and holds it there. A new ball
  is launched automatically.
* `frame`: a decision every step: left, right or stay, plus launch while no ball is in play. The game also ends
  after `idle_cap` steps in a row without a ball in play: nothing can happen until the player launches one, so a
  player that never does would otherwise spend the rest of `step_cap` on steps that change nothing (Snake ends a
  game without food for the same reason).

Score: the game's points, over a full game (5 lives) on the macro track and within `step_cap` steps on the frame
track.

Pressing left or right moves the paddle about 12 pixels in that step and about 11 more in the next (measured),
so the controller plans a few steps ahead.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from arena.core import JSON, DecisionPoint, Metric, Option, Question
from arena.games.atari import AleGame, Motion, describe_motion, motion, reflect

WIDTH = 144
PADDLE_Y = 157
PADDLE_ROW = 190  # screen row through the paddle
SCREEN_LEFT = 8
TOP_WALL = 32  # screen row of field y 0
BRICK_ROWS = 6
BRICKS_PER_ROW = 18
BRICK_TOP = 25  # field y of the first brick row
BRICK_HEIGHT = 6
BRICK_WIDTH = 8
ROW_POINTS = (7, 7, 4, 4, 1, 1)
ZONES = 8
ZONE_SIZE = WIDTH // ZONES
NOOP, FIRE, RIGHT, LEFT = 0, 1, 2, 3
PUSH = {LEFT: -1, NOOP: 0, RIGHT: 1, FIRE: 0}
NOW, NEXT, HORIZON = 12.0, 11.0, 3
PADDLE_RANGE = (0, 136)


def _ball(ram: npt.NDArray[np.uint8]) -> tuple[int, int] | None:
    if int(ram[101]) == 0:
        return None
    return int(ram[99]) - 57, int(ram[101]) - 23


class Breakout(AleGame):
    env_id = "ALE/Breakout-v5"

    def __init__(self, sticky: float) -> None:
        super().__init__(sticky)
        self.last_action = NOOP

    def reset(self, seed: int) -> None:
        super().reset(seed)
        self.last_action = NOOP

    def step(self, action: int) -> float:
        reward = super().step(action)
        self.last_action = action
        return reward

    def ball(self) -> tuple[int, int] | None:
        return _ball(self.ram)

    def motion(self) -> Motion | None:
        return motion([_ball(ram) for ram in self.history])

    def paddle_left(self) -> int:
        return int(self.ram[72]) - 55

    def paddle_span(self) -> tuple[int, int]:
        """The paddle's span: its left edge from RAM, its width (16, or 8 once it shrinks) from the screen.
        Only the lit run starting at the paddle counts, so a ball passing the same row is not mistaken for it."""
        left = self.paddle_left()
        row = np.any(self.screen()[PADDLE_ROW, SCREEN_LEFT : SCREEN_LEFT + WIDTH] != 0, axis=1)
        start = next((x for x in (left, left - 1, left + 1) if 0 <= x < WIDTH and row[x]), None)
        if start is None:
            return left, left + 15
        width = 0
        while start + width < WIDTH and row[start + width] and width < 16:
            width += 1
        width = 16 if width > 12 else 8
        return start, start + width - 1

    def lives(self) -> int:
        return int(self.ram[57])

    def bricks(self) -> list[str]:
        """Six rows of eighteen, top row first: '#' standing, '.' broken. Read from the screen."""
        screen = self.screen()
        rows = []
        for r in range(BRICK_ROWS):
            y0 = TOP_WALL + BRICK_TOP + r * BRICK_HEIGHT
            line = ""
            for k in range(BRICKS_PER_ROW):
                x0 = SCREEN_LEFT + k * BRICK_WIDTH
                cell = screen[y0 : y0 + BRICK_HEIGHT, x0 : x0 + BRICK_WIDTH]
                line += "#" if np.count_nonzero(np.any(cell != 0, axis=2)) > cell.shape[0] * cell.shape[1] // 2 else "."
            rows.append(line)
        return rows


def zone_bounds(zone: int) -> tuple[int, int]:
    return (zone - 1) * ZONE_SIZE, zone * ZONE_SIZE - 1


def zone_of(x: float) -> int:
    return min(max(int(x) // ZONE_SIZE + 1, 1), ZONES)


def steer(paddle_left: int, last_action: int, target_x: float) -> int:
    """The action whose best continuation brings the paddle centre closest to `target_x`."""
    best_cost, best_action = float("inf"), NOOP
    for plan in itertools.product((NOOP, LEFT, RIGHT), repeat=HORIZON):
        left = float(paddle_left)
        previous = last_action
        cost = 0.0
        for k, action in enumerate(plan):
            left = min(max(left + NOW * PUSH[action] + NEXT * PUSH[previous], PADDLE_RANGE[0]), PADDLE_RANGE[1])
            previous = action
            cost += abs(left + 8 - target_x) * (1.0 if k == HORIZON - 1 else 0.3)
        if cost < best_cost - 1e-9:
            best_cost, best_action = cost, plan[0]
    return best_action


def intercept_x(m: Motion) -> float | None:
    """Where the falling ball's centre reaches the paddle's top edge, bouncing off the side walls."""
    if m.dy <= 0:
        return None
    steps = (PADDLE_Y - (m.y + 4)) / m.dy
    return reflect(m.x + 1 + m.dx * steps, 1, WIDTH - 2)


# --- text ---------------------------------------------------------------------------------------------

HEADER = (
    "Breakout. You control the paddle at the bottom of a field 144 wide (x 0 at the left wall) whose top edge is "
    "y 0; the paddle's top edge is at y 157. The ball bounces off the walls, the bricks and your paddle; each brick "
    "it hits breaks and scores points. A ball that falls past your paddle costs a life; the game ends with no lives."
)

MACRO_INSTRUCTIONS = (
    "Choose the band of the field where your paddle should be. Your paddle moves to the middle of that band and "
    "stays there until the next decision. Goal: score as many points as possible."
)

FRAME_INSTRUCTIONS = (
    "Choose what to do with your paddle during this step. A push keeps moving the paddle a little during the next "
    "step. Goal: score as many points as possible."
)

FRAME_TEXT = {
    "left": "push your paddle left",
    "right": "push your paddle right",
    "stay": "do not push your paddle",
    "launch": "launch a new ball",
}
FRAME_ACTIONS = {"left": LEFT, "right": RIGHT, "stay": NOOP, "launch": FIRE}


def render_state(game: Breakout, step_cap: int, idle: tuple[int, int] | None = None) -> str:
    """`idle` is (steps without a ball in play so far, the cap on them) where that cap applies."""
    rule = f"The game also ends after {step_cap} steps (a step is 4 frames, 1/15 of a second)"
    if idle is not None:
        rule += f", or after {idle[1]} steps in a row without a ball in play"
    lines = [f"{HEADER} {rule}.", f"Step {game.steps} of {step_cap}. Score: {int(game.total)}. Lives: {game.lives()}."]
    m = game.motion()
    ball = game.ball()
    if ball is None and idle is not None:
        lines.append(f"No ball is in play; the game ends unless one is launched within {idle[1] - idle[0]} steps.")
    elif ball is None:
        lines.append("No ball is in play.")
    elif m is None:
        lines.append(f"The ball is at x {ball[0]}, y {ball[1]}; it has just appeared.")
    else:
        lines.append(f"The ball is at x {m.x}, y {m.y}; it {describe_motion(m, ('right', 'left'), ('down', 'up'))}.")
    left, right = game.paddle_span()
    lines.append(f"Your paddle covers x {left}-{right}.")
    bricks = game.bricks()
    standing = sum(row.count("#") for row in bricks)
    lines.append(f"Bricks standing: {standing} of {BRICK_ROWS * BRICKS_PER_ROW} (# standing, . broken; 8 wide each):")
    for r, row in enumerate(bricks):
        y0 = BRICK_TOP + r * BRICK_HEIGHT
        points = f"{ROW_POINTS[r]} point" + ("s" if ROW_POINTS[r] != 1 else "")
        lines.append(f"row {r + 1} (y {y0}-{y0 + BRICK_HEIGHT - 1}, {points}): {row}")
    return "\n".join(lines)


def snapshot(game: Breakout) -> JSON:
    ball = game.ball()
    return {
        "field": [WIDTH, PADDLE_Y + 4],
        "ball": list(ball) if ball else None,
        "paddle": list(game.paddle_span()),
        "lives": game.lives(),
        "score": int(game.total),
        "bricks": game.bricks(),
    }


@dataclass(frozen=True, slots=True)
class BreakoutView:
    motion: Motion | None
    ball: tuple[int, int] | None
    paddle_left: int
    last_action: int


class _BreakoutTask:
    game = "breakout"
    track = ""
    default_key = ""

    def __init__(self, sticky: float) -> None:
        self.ale = Breakout(sticky)

    @property
    def steps(self) -> int:
        return self.ale.steps

    def score(self) -> float:
        return self.ale.total

    def metrics(self) -> dict[str, Metric]:
        standing = sum(row.count("#") for row in self.ale.bricks())
        return {
            "bricks_broken": BRICK_ROWS * BRICKS_PER_ROW - standing,
            "lives": self.ale.lives(),
            "game_over": self.ale.over,
        }

    def snapshot(self) -> JSON:
        return snapshot(self.ale)

    def held(self, key: str) -> str:
        return key  # a push is held until the next decision lands

    def close(self) -> None:
        self.ale.close()

    def _view(self) -> BreakoutView:
        a = self.ale
        return BreakoutView(a.motion(), a.ball(), a.paddle_left(), a.last_action)


class BreakoutMacro(_BreakoutTask):
    track = "macro"

    def __init__(self, step_cap: int = 10_000, sticky: float = 0.25) -> None:
        super().__init__(sticky)
        self.step_cap = step_cap
        self.band = zone_bounds(ZONES // 2)
        self._heading = (0, 0)

    def reset(self, seed: int) -> None:
        self.ale.reset(seed)
        self.band = zone_bounds(ZONES // 2)
        self._heading = (0, 0)
        self._advance()

    @property
    def done(self) -> bool:
        return self.ale.over or self.ale.steps >= self.step_cap

    def _advance(self) -> None:
        """Run the controller until the ball's heading differs from the one at the last decision: any vertical
        change, or a horizontal change while the ball falls. Launches new balls on its own."""
        low, high = self.band
        while not self.done:
            if self.ale.ball() is None:
                self._heading = (0, 0)
                self.ale.step(FIRE)
                continue
            self.ale.step(steer(self.ale.paddle_left(), self.ale.last_action, (low + high) / 2))
            m = self.ale.motion()
            if m is None or m.window < 2:
                continue
            heading = ((m.dx > 0) - (m.dx < 0), (m.dy > 0) - (m.dy < 0))
            turned = heading[1] != self._heading[1]
            bounced = heading[1] > 0 and heading[0] != 0 and heading[0] != self._heading[0]
            if turned or bounced:
                self._heading = heading
                return

    def decision_point(self) -> DecisionPoint:
        left, right = self.ale.paddle_span()
        here = zone_of((left + right) / 2)
        options = []
        for zone in range(1, ZONES + 1):
            low, high = zone_bounds(zone)
            text = f"band {zone}: x {low}-{high}"
            if zone == here:
                text += " (your paddle is centred in this band now)"
            options.append(Option(f"zone{zone}", text))
        question = Question(render_state(self.ale, self.step_cap), MACRO_INSTRUCTIONS, tuple(options))
        return DecisionPoint(question, self._view())

    def apply(self, key: str) -> None:
        zone = int(key.removeprefix("zone"))
        if not 1 <= zone <= ZONES:
            raise ValueError(f"unknown Breakout band {key!r}")
        self.band = zone_bounds(zone)
        self._advance()


class BreakoutFrame(_BreakoutTask):
    track = "frame"
    default_key = "stay"

    def __init__(self, step_cap: int = 1500, idle_cap: int = 300, sticky: float = 0.25) -> None:
        super().__init__(sticky)
        self.step_cap = step_cap
        self.idle_cap = idle_cap
        self.idle = 0  # steps in a row that ended without a ball in play

    def reset(self, seed: int) -> None:
        self.ale.reset(seed)
        self.idle = 0

    @property
    def done(self) -> bool:
        return self.ale.over or self.ale.steps >= self.step_cap or self.idle >= self.idle_cap

    def decision_point(self) -> DecisionPoint:
        keys = ["left", "right", "stay"] + (["launch"] if self.ale.ball() is None else [])
        options = tuple(Option(key, FRAME_TEXT[key]) for key in keys)
        state = render_state(self.ale, self.step_cap, (self.idle, self.idle_cap))
        return DecisionPoint(Question(state, FRAME_INSTRUCTIONS, options), self._view())

    def apply(self, key: str) -> None:
        self.ale.step(FRAME_ACTIONS.get(key, NOOP))
        self.idle = self.idle + 1 if self.ale.ball() is None else 0

    def metrics(self) -> dict[str, Metric]:
        return {**super().metrics(), "idle_end": self.idle >= self.idle_cap}


# --- reference player -----------------------------------------------------------------------------------


def reference_target(view: BreakoutView) -> float:
    """Meet the falling ball where it reaches the paddle; otherwise stay under it (or wait in the middle)."""
    if view.motion is not None:
        x = intercept_x(view.motion)
        if x is not None:
            return x
    if view.ball is not None:
        return view.ball[0] + 1
    return WIDTH / 2


def reference_macro(view: BreakoutView) -> str:
    return f"zone{zone_of(reference_target(view))}"


def reference_frame(view: BreakoutView) -> str:
    if view.ball is None:
        return "launch"
    action = steer(view.paddle_left, view.last_action, reference_target(view))
    return {LEFT: "left", RIGHT: "right"}.get(action, "stay")
