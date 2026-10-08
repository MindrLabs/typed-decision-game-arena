"""One episode: the decision loop, on the turn-based tracks and with reaction time on the real-time track.

Turn-based (`delay_steps == 0`): the game waits for every decision, and the chosen key is applied at once.

Real-time (`delay_steps == k >= 1`): a player that observes the game at step t answers at step t + k, and is
busy with the next decision from then on. So the key chosen from the observation at t is applied at step t + k,
and in between the game runs on what was decided before (`Task.held`: a paddle push stays pushed, a Tetris key
press acts once and is followed by waiting). Every decision therefore acts on a picture k steps old.

On the real-time track the state text ends with one line saying so, and which earlier choice takes effect now:
a real-time player knows what it decided last.

A question with a single legal option is not asked: the move is forced for every player alike.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from arena.core import JSON, Decision, DecisionPoint, Metric, Player, Question, Task
from arena.seeding import Rng


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    index: int
    step: int
    snapshot: JSON
    question: Question
    decision: Decision


@dataclass(frozen=True, slots=True)
class Outcome:
    score: float
    metrics: dict[str, Metric]
    decisions: int
    forced: int
    calls: int
    steps: int


def decision_rng(suite_id: str, board: str, game: str, seed: int, index: int) -> Rng:
    """The stream for option orders and tie-breaks of one decision. It does not depend on the player, so two
    players facing the same position at the same point of the same seed see the same order."""
    return Rng.derive(suite_id, board, game, seed, index, "decide")


def realtime_note(delay_steps: int, pending: str) -> str:
    steps = "1 step" if delay_steps == 1 else f"{delay_steps} steps"
    return (
        f"Real time: the game does not wait for you. Each choice takes effect {steps} after the position it was "
        f"made from. Your previous choice, '{pending}', takes effect now; this one takes effect {steps} later."
    )


def play(
    task: Task,
    player: Player,
    seed: int,
    *,
    suite_id: str,
    board: str,
    delay_steps: int = 0,
    on_decision: Callable[[DecisionRecord], None] | None = None,
) -> Outcome:
    if delay_steps < 0:
        raise ValueError("delay_steps must be >= 0")
    task.reset(seed)
    player.start(seed)
    pending = task.default_key
    index = forced = calls = 0
    while not task.done:
        point = task.decision_point()
        if delay_steps:
            q = point.question
            note = realtime_note(delay_steps, pending)
            point = DecisionPoint(Question(f"{q.state}\n{note}", q.instructions, q.options), point.view)
        record_step, snapshot = task.steps, task.snapshot()
        options = point.question.options
        if len(options) == 1:
            decision = Decision(options[0].key, (), forced=True)
            forced += 1
        else:
            decision = player.decide(point, decision_rng(suite_id, board, task.game, seed, index))
            if decision.choice not in point.question.keys:
                raise ValueError(f"{player.id} chose {decision.choice!r}, not an option of decision {index}")
            calls += len(decision.calls)
        if on_decision is not None:
            on_decision(DecisionRecord(index, record_step, snapshot, point.question, decision))
        if delay_steps == 0:
            task.apply(decision.choice)
        else:
            for i in range(delay_steps):
                task.apply(pending if i == 0 else task.held(pending))
                if task.done:
                    break
            pending = decision.choice
        index += 1
    return Outcome(task.score(), task.metrics(), index, forced, calls, task.steps)
