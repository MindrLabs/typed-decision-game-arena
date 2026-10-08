"""The Arcade Learning Environment under one fixed configuration, shared by Pong and Breakout.

Settings follow Machado et al. (2018), "Revisiting the Arcade Learning Environment": `frameskip=4` and sticky
actions with probability 0.25 (the ALE v5 default). Sticky actions are what make seeds differ: the console
itself is deterministic, so with `repeat_action_probability=0` every seed replays the same game for a
deterministic player. The seed passed to `reset` seeds ALE's own generator, so a (seed, action sequence) pair
always reproduces the same frames.

RAM addresses follow the AtariARI annotations (Anand et al. 2019, "Unsupervised State Representation Learning in
Atari"); the screen-coordinate offsets were measured against rendered frames and are pinned by tests.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass
from typing import Any

import ale_py
import gymnasium as gym
import numpy as np
import numpy.typing as npt

gym.register_envs(ale_py)

FRAMESKIP = 4
STICKY = 0.25


@dataclass(frozen=True, slots=True)
class Motion:
    """Ball position and how far it moved over the last `window` steps (1 or 2), in field coordinates."""

    x: int
    y: int
    moved_x: int
    moved_y: int
    window: int

    @property
    def dx(self) -> float:
        return self.moved_x / self.window

    @property
    def dy(self) -> float:
        return self.moved_y / self.window


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def motion(positions: list[tuple[int, int] | None]) -> Motion | None:
    """Motion from the latest positions (oldest first).

    When the last three single-step displacements point the same way on both axes, the motion is *settled* and
    covers the last two steps, which smooths the sub-pixel jitter of single steps (a ball at 6 pixels per step
    moves 4, 8, 4, 8). Otherwise it covers the last step only: right after a bounce a single step can straddle
    the wall and understate the speed, so callers that predict should wait for a settled motion."""
    if len(positions) < 2 or positions[-1] is None or positions[-2] is None:
        return None
    (x, y), (x1, y1) = positions[-1], positions[-2]
    if len(positions) >= 4 and all(p is not None for p in positions[-4:]):
        points = [p for p in positions[-4:] if p is not None]
        steps = [(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(points)]
        if len({_sign(dx) for dx, _ in steps}) == 1 and len({_sign(dy) for _, dy in steps}) == 1:
            x0, y0 = points[-3]
            return Motion(x, y, x - x0, y - y0, 2)
    return Motion(x, y, x - x1, y - y1, 1)


class AleGame:
    """One ALE environment with RAM observations. Steps are agent steps (`FRAMESKIP` frames each)."""

    env_id = ""

    def __init__(self, sticky: float = STICKY) -> None:
        self.env: Any = gym.make(
            self.env_id,
            obs_type="ram",
            frameskip=FRAMESKIP,
            repeat_action_probability=sticky,
            full_action_space=False,
        )
        self.ram: npt.NDArray[np.uint8] = np.zeros(128, dtype=np.uint8)
        self.history: deque[npt.NDArray[np.uint8]] = deque(maxlen=4)
        self.total = 0.0
        self.steps = 0
        self.over = False

    def reset(self, seed: int) -> None:
        ram, _ = self.env.reset(seed=seed)
        self.ram = np.asarray(ram, dtype=np.uint8)
        self.history = deque([self.ram], maxlen=4)
        self.total = 0.0
        self.steps = 0
        self.over = False

    def step(self, action: int) -> float:
        ram, reward, terminated, truncated, _ = self.env.step(action)
        self.ram = np.asarray(ram, dtype=np.uint8)
        self.history.append(self.ram)
        self.total += float(reward)
        self.steps += 1
        self.over = bool(terminated or truncated)
        return float(reward)

    @property
    def previous(self) -> npt.NDArray[np.uint8]:
        return self.history[-2] if len(self.history) > 1 else self.ram

    def screen(self) -> npt.NDArray[np.uint8]:
        return np.asarray(self.env.unwrapped.ale.getScreenRGB(), dtype=np.uint8)

    def ram_hash(self) -> str:
        return bytes(self.ram).hex()

    def close(self) -> None:
        self.env.close()


def reflect(position: float, low: float, high: float) -> float:
    """Fold a coordinate back into [low, high] as a ball bouncing between two walls would."""
    span = high - low
    if span <= 0:
        return low
    offset = (position - low) % (2 * span)
    return low + (offset if offset <= span else 2 * span - offset)


def describe_motion(m: Motion, horizontal: tuple[str, str], vertical: tuple[str, str]) -> str:
    """'moved 8 right and 12 down over the last 2 steps' (or 'did not move ...')."""
    parts = []
    for value, (positive, negative) in ((m.moved_x, horizontal), (m.moved_y, vertical)):
        if value:
            parts.append(f"{abs(value)} {positive if value > 0 else negative}")
    steps = "the last step" if m.window == 1 else f"the last {m.window} steps"
    return f"moved {' and '.join(parts)} over {steps}" if parts else f"did not move over {steps}"
