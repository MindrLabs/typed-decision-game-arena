"""The decision loop's timing rules, on a tiny fake task that records every key it receives."""

from __future__ import annotations

from arena.core import JSON, Decision, DecisionPoint, Metric, Option, Question
from arena.episode import play, realtime_note
from arena.seeding import Rng


class Counter:
    """A task whose state is the step count; the only options are 'a' and 'b' (or just 'a' every 3rd step)."""

    game = "counter"
    track = "frame"
    default_key = "idle"

    def __init__(self, length: int = 6, hold: bool = True) -> None:
        self.length = length
        self.hold = hold
        self.applied: list[str] = []

    def reset(self, seed: int) -> None:
        self.applied = []

    @property
    def done(self) -> bool:
        return len(self.applied) >= self.length

    @property
    def steps(self) -> int:
        return len(self.applied)

    def decision_point(self) -> DecisionPoint:
        keys = ("a",) if self.steps % 3 == 2 else ("a", "b")
        return DecisionPoint(Question(f"step {self.steps}", "go", tuple(Option(k, k) for k in keys)))

    def apply(self, key: str) -> None:
        self.applied.append(key)

    def held(self, key: str) -> str:
        return key if self.hold else "wait"

    def score(self) -> float:
        return float(self.applied.count("b"))

    def metrics(self) -> dict[str, Metric]:
        return {}

    def snapshot(self) -> JSON:
        return {"steps": self.steps}

    def close(self) -> None:
        pass


class AlwaysB:
    id = "always-b"
    seen: list[str]

    def __init__(self) -> None:
        self.seen = []

    def start(self, seed: int) -> None:
        pass

    def decide(self, point: DecisionPoint, rng: Rng) -> Decision:
        self.seen.append(point.question.state)
        return Decision("b" if "b" in point.question.keys else "a")

    def close(self) -> None:
        pass


def test_turn_based_applies_each_choice_at_once_and_skips_forced_moves() -> None:
    task, player = Counter(), AlwaysB()
    outcome = play(task, player, 1, suite_id="t", board="frame")
    assert task.applied == ["b", "b", "a", "b", "b", "a"]
    assert outcome.decisions == 6
    assert outcome.forced == 2
    assert len(player.seen) == 4  # forced moves are not asked


def test_real_time_applies_choices_late_and_holds_them() -> None:
    task, player = Counter(length=6), AlwaysB()
    play(task, player, 1, suite_id="t", board="realtime", delay_steps=2)
    # the first two steps run on the default key; the choice made at step 0 lands at step 2 and is held through
    # step 3; the forced move seen at step 2 lands at step 4
    assert task.applied == ["idle", "idle", "b", "b", "a", "a"]
    assert player.seen[0].endswith(realtime_note(2, "idle"))


def test_real_time_key_presses_act_once() -> None:
    task, player = Counter(length=6, hold=False), AlwaysB()
    play(task, player, 1, suite_id="t", board="realtime", delay_steps=3)
    assert task.applied == ["idle", "wait", "wait", "b", "wait", "wait"]


def test_records_every_decision() -> None:
    records: list[int] = []
    play(Counter(), AlwaysB(), 1, suite_id="t", board="frame", on_decision=lambda r: records.append(r.index))
    assert records == list(range(6))
