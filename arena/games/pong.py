"""Atari Pong (ALE `Pong-v5`): the player holds the right paddle against the built-in opponent.

Field coordinates: x 0-159 from the left, y 0-159 from the top of the playing field. The player's paddle sits at
x 140-143 and is 16 pixels tall; the ball is 2 x 4 pixels and its position is its top-left corner.

* `macro`: a decision whenever the ball starts moving towards the player, bounces off the top or bottom edge on
  its way in, or starts moving away (each time once three consistent steps show the new direction). The player
  picks one of 8 horizontal bands, 20 pixels each; a fixed controller moves the paddle centre to the middle of
  that band and holds it there until the next decision. A paddle centred on a band covers every ball that
  arrives inside it, so the decision is where the ball will arrive.
* `frame`: a decision every step: up, down or stay.

Score: points won minus points lost (the game's own reward), over a full game on the macro track and within
`step_cap` steps on the frame track.

The paddle has momentum (measured: velocity' = 0.55 velocity + 10 per step of pressing), so the controller looks
a few steps ahead instead of reacting to the current gap; a plain bang-bang controller oscillates.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from arena.core import JSON, DecisionPoint, Metric, Option, Question
from arena.games.atari import AleGame, Motion, describe_motion, motion, reflect

FIELD = 160
PADDLE_HEIGHT = 16
PLAYER_X = (140, 143)
OPPONENT_X = (16, 19)
ZONES = 8
ZONE_SIZE = FIELD // ZONES
NOOP, UP, DOWN = 0, 2, 3  # ALE's RIGHT moves the right paddle up, LEFT moves it down
PUSH = {UP: -1, NOOP: 0, DOWN: 1}
DECAY, ACCEL, HORIZON = 0.55, 10.0, 4


def _ball(ram: npt.NDArray[np.uint8]) -> tuple[int, int] | None:
    # Before the first serve the console leaves a vertical position with no horizontal one (x would read -49);
    # the screen shows no ball then.
    if int(ram[54]) == 0 or int(ram[49]) == 0:
        return None
    return int(ram[49]) - 49, int(ram[54]) - 48


def _player_top(ram: npt.NDArray[np.uint8]) -> int:
    return int(ram[51]) - 48


class Pong(AleGame):
    env_id = "ALE/Pong-v5"

    def ball(self) -> tuple[int, int] | None:
        return _ball(self.ram)

    def motion(self) -> Motion | None:
        return motion([_ball(ram) for ram in self.history])

    def player_top(self) -> int:
        return _player_top(self.ram)

    def player_velocity(self) -> int:
        return _player_top(self.ram) - _player_top(self.previous)

    def opponent_top(self) -> int:
        return int(self.ram[50]) - 49

    def score(self) -> tuple[int, int]:
        return int(self.ram[14]), int(self.ram[13])


def span(top: int) -> tuple[int, int] | None:
    """The visible part of a paddle whose top edge is at `top`; None while it is off the field (the opponent's
    paddle is, for the first steps of a game)."""
    low, high = max(top, 0), min(top + PADDLE_HEIGHT - 1, FIELD - 1)
    return (low, high) if low <= high else None


def zone_bounds(zone: int) -> tuple[int, int]:
    return (zone - 1) * ZONE_SIZE, zone * ZONE_SIZE - 1


def zone_of(y: float) -> int:
    return min(max(int(y) // ZONE_SIZE + 1, 1), ZONES)


def steer(paddle_top: int, velocity: int, target_y: float) -> int:
    """Pick the action whose best continuation brings the paddle centre closest to `target_y` within
    `HORIZON` steps, using the measured paddle dynamics."""
    best_cost, best_action = float("inf"), NOOP
    for plan in itertools.product((NOOP, UP, DOWN), repeat=HORIZON):
        centre = paddle_top + PADDLE_HEIGHT / 2
        v = float(velocity)
        cost = 0.0
        for k, action in enumerate(plan):
            v = DECAY * v + ACCEL * PUSH[action]
            centre += v
            cost += abs(centre - target_y) * (1.0 if k == HORIZON - 1 else 0.3)
        if cost < best_cost - 1e-9:
            best_cost, best_action = cost, plan[0]
    return best_action


def intercept_y(m: Motion) -> float | None:
    """Where the ball centre crosses the front of the player's paddle, bouncing off the field edges,
    if it is moving towards the player."""
    if m.dx <= 0:
        return None
    steps = (PLAYER_X[0] - (m.x + 2)) / m.dx
    return reflect(m.y + 2 + m.dy * steps, 2, FIELD - 3)


# --- text ---------------------------------------------------------------------------------------------

HEADER = (
    "Pong. You control the right paddle (x 140-143); the opponent controls the left paddle (x 16-19). The field "
    "is 160 wide (x 0 at the left) and 160 tall (y 0 at the top). Paddles are 16 tall and move only up and down. "
    "The ball bounces off the top and bottom edges and off the paddles; a ball that gets past a paddle scores "
    "a point for the other side. The first side to 21 points wins."
)

MACRO_INSTRUCTIONS = (
    "Choose the band of the field where your paddle should be. Your paddle moves to the middle of that band and "
    "stays there until the next decision; centred there, it covers the whole band. "
    "Goal: win as many points as possible."
)

FRAME_INSTRUCTIONS = (
    "Choose how to push your paddle during this step. The paddle keeps some speed from earlier steps. "
    "Goal: win as many points as possible."
)

FRAME_TEXT = {"up": "push your paddle up", "down": "push your paddle down", "stay": "do not push your paddle"}
FRAME_ACTIONS = {"up": UP, "down": DOWN, "stay": NOOP}


def _paddle_text(owner: str, place: tuple[int, int] | None) -> str:
    return f"{owner} paddle is not on the field" if place is None else f"{owner} paddle covers y {place[0]}-{place[1]}"


def render_state(game: Pong, step_cap: int) -> str:
    me, them = game.score()
    lines = [
        f"{HEADER} The game also ends after {step_cap} steps (a step is 4 frames, 1/15 of a second).",
        f"Step {game.steps} of {step_cap}. Score: you {me}, opponent {them}.",
    ]
    m = game.motion()
    ball = game.ball()
    if ball is None:
        lines.append("No ball is in play.")
    elif m is None:
        lines.append(f"The ball is at x {ball[0]}, y {ball[1]}; it has just appeared.")
    else:
        lines.append(f"The ball is at x {m.x}, y {m.y}; it {describe_motion(m, ('right', 'left'), ('down', 'up'))}.")
    velocity = game.player_velocity()
    moving = f"moved {abs(velocity)} {'down' if velocity > 0 else 'up'}" if velocity else "did not move"
    yours = _paddle_text("Your", span(game.player_top()))
    theirs = _paddle_text("The opponent's", span(game.opponent_top()))
    lines.append(f"{yours} and {moving} over the last step. {theirs}.")
    return "\n".join(lines)


def _listed(place: tuple[int, int] | None) -> list[int] | None:
    return None if place is None else list(place)


def snapshot(game: Pong) -> JSON:
    me, them = game.score()
    ball = game.ball()
    return {
        "field": [FIELD, FIELD],
        "ball": list(ball) if ball else None,
        "player": _listed(span(game.player_top())),
        "opponent": _listed(span(game.opponent_top())),
        "score": [me, them],
    }


@dataclass(frozen=True, slots=True)
class PongView:
    motion: Motion | None
    ball: tuple[int, int] | None
    paddle_top: int
    paddle_velocity: int


class _PongTask:
    game = "pong"
    track = ""
    default_key = ""

    def __init__(self, sticky: float) -> None:
        self.ale = Pong(sticky)

    @property
    def steps(self) -> int:
        return self.ale.steps

    def score(self) -> float:
        return self.ale.total

    def metrics(self) -> dict[str, Metric]:
        me, them = self.ale.score()
        return {"points_won": me, "points_lost": them, "game_over": self.ale.over}

    def snapshot(self) -> JSON:
        return snapshot(self.ale)

    def held(self, key: str) -> str:
        return key  # a push is held until the next decision lands

    def close(self) -> None:
        self.ale.close()

    def _view(self) -> PongView:
        a = self.ale
        return PongView(a.motion(), a.ball(), a.player_top(), a.player_velocity())


class PongMacro(_PongTask):
    track = "macro"

    def __init__(self, step_cap: int = 20_000, sticky: float = 0.25) -> None:
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

    def _target(self) -> float:
        low, high = self.band
        return (low + high) / 2

    def _advance(self) -> None:
        """Run the controller until the ball's heading differs from the one at the last decision: any horizontal
        change, or a vertical change while the ball comes in. A decision waits for two consistent steps after
        the change, so the reported motion never straddles a bounce."""
        while not self.done:
            self.ale.step(steer(self.ale.player_top(), self.ale.player_velocity(), self._target()))
            if self.ale.ball() is None:
                self._heading = (0, 0)
                continue
            m = self.ale.motion()
            if m is None or m.window < 2:
                continue
            heading = ((m.dx > 0) - (m.dx < 0), (m.dy > 0) - (m.dy < 0))
            turned = heading[0] != self._heading[0]
            bounced = heading[0] > 0 and heading[1] != 0 and heading[1] != self._heading[1]
            if turned or bounced:
                self._heading = heading
                return

    def decision_point(self) -> DecisionPoint:
        place = span(self.ale.player_top())
        here = zone_of((place[0] + place[1]) / 2) if place else None
        options = []
        for zone in range(1, ZONES + 1):
            low, high = zone_bounds(zone)
            text = f"band {zone}: y {low}-{high}"
            if zone == here:
                text += " (your paddle is centred in this band now)"
            options.append(Option(f"zone{zone}", text))
        question = Question(render_state(self.ale, self.step_cap), MACRO_INSTRUCTIONS, tuple(options))
        return DecisionPoint(question, self._view())

    def apply(self, key: str) -> None:
        zone = int(key.removeprefix("zone"))
        if not 1 <= zone <= ZONES:
            raise ValueError(f"unknown Pong band {key!r}")
        self.band = zone_bounds(zone)
        self._advance()


class PongFrame(_PongTask):
    track = "frame"
    default_key = "stay"

    def __init__(self, step_cap: int = 1500, sticky: float = 0.25) -> None:
        super().__init__(sticky)
        self.step_cap = step_cap

    def reset(self, seed: int) -> None:
        self.ale.reset(seed)

    @property
    def done(self) -> bool:
        return self.ale.over or self.ale.steps >= self.step_cap

    def decision_point(self) -> DecisionPoint:
        options = tuple(Option(key, FRAME_TEXT[key]) for key in ("up", "down", "stay"))
        state = render_state(self.ale, self.step_cap)
        return DecisionPoint(Question(state, FRAME_INSTRUCTIONS, options), self._view())

    def apply(self, key: str) -> None:
        self.ale.step(FRAME_ACTIONS.get(key, NOOP))


# --- reference player -----------------------------------------------------------------------------------


def reference_target(view: PongView) -> float:
    """Meet the ball where it will cross the paddle; otherwise follow it (or wait in the middle)."""
    if view.motion is not None:
        y = intercept_y(view.motion)
        if y is not None:
            return y
    if view.ball is not None:
        return view.ball[1] + 2
    return FIELD / 2


def reference_macro(view: PongView) -> str:
    return f"zone{zone_of(reference_target(view))}"


def reference_frame(view: PongView) -> str:
    action = steer(view.paddle_top, view.paddle_velocity, reference_target(view))
    return {UP: "up", DOWN: "down"}.get(action, "stay")
