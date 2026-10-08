"""Types shared by games, tracks, players and the runner."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from arena.seeding import Rng

type JSON = dict[str, Any]
type Metric = float | int | bool | str


@dataclass(frozen=True, slots=True)
class Option:
    """One legal move as the model reads it: a stable key and the sentence describing it."""

    key: str
    text: str


@dataclass(frozen=True, slots=True)
class Question:
    """Everything a text player sees for one decision. Options are in the engine's canonical order;
    the decision protocol decides the order (and grouping) actually shown."""

    state: str
    instructions: str
    options: tuple[Option, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("a question needs at least one option")
        keys = [option.key for option in self.options]
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate option keys: {keys}")

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(option.key for option in self.options)

    def option(self, key: str) -> Option:
        for option in self.options:
            if option.key == key:
                return option
        raise KeyError(key)

    def reordered(self, keys: Sequence[str]) -> Question:
        """The same question showing only `keys`, in that order."""
        return Question(self.state, self.instructions, tuple(self.option(key) for key in keys))

    def to_json(self) -> JSON:
        return {
            "state": self.state,
            "instructions": self.instructions,
            "options": [{"key": option.key, "text": option.text} for option in self.options],
        }


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    """A question plus a structured view of the same position for non-text baselines.
    The view never reaches a model."""

    question: Question
    view: Any = None


@dataclass(frozen=True, slots=True)
class Call:
    """One request to a text player: the options shown, in order, and what came back."""

    stage: str
    keys: tuple[str, ...]
    choice: str
    probabilities: dict[str, float] | None
    latency_ms: float

    def to_json(self) -> JSON:
        return {
            "stage": self.stage,
            "keys": list(self.keys),
            "choice": self.choice,
            "p": self.probabilities,
            "ms": round(self.latency_ms, 3),
        }


@dataclass(frozen=True, slots=True)
class Decision:
    choice: str
    calls: tuple[Call, ...] = ()
    forced: bool = False


class Task(Protocol):
    """One game played on one track. Deterministic given the seed and the keys applied."""

    game: str
    track: str
    #: Key held before a player's first decision lands (real-time track).
    default_key: str

    def reset(self, seed: int) -> None: ...

    @property
    def done(self) -> bool: ...

    @property
    def steps(self) -> int:
        """Environment steps elapsed (one per decision on frame tracks, often many on macro tracks)."""
        ...

    def decision_point(self) -> DecisionPoint: ...

    def apply(self, key: str) -> None:
        """Play `key`. Frame tracks accept any key of their action vocabulary and treat an illegal one as
        doing nothing, so a key chosen earlier can still be applied on the real-time track."""
        ...

    def held(self, key: str) -> str:
        """The key in effect on the steps after `key` was applied while no new decision has landed (real-time
        track): the key itself for a held control such as a paddle push, `wait` for a key press."""
        ...

    def score(self) -> float: ...

    def metrics(self) -> dict[str, Metric]: ...

    def snapshot(self) -> JSON:
        """Compact JSON of the position for replays and the site."""
        ...

    def close(self) -> None:
        """Release resources (the ALE emulator); the task is not used afterwards."""
        ...


class Player(Protocol):
    id: str

    def start(self, seed: int) -> None:
        """Called before each episode (stateful baselines reset here)."""
        ...

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision: ...

    def close(self) -> None: ...


class PlayerError(RuntimeError):
    """A player failed to answer after its retries (server down, bad response)."""
