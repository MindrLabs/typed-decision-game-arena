"""Fixed question sets for diagnostics (latency, position bias).

Questions come from the reference player's games on probe seeds (outside every dev and test range), sampled at a
fixed stride and cut to one request the way the protocol shows it. They depend on nothing but the suite, so every
model is timed and probed on byte-identical inputs.
"""

from __future__ import annotations

from collections.abc import Iterator

from arena.core import Call, PlayerError, Question
from arena.episode import decision_rng
from arena.players import ReferencePlayer, TextPlayer
from arena.suite import Suite
from arena.tasks import make_task

PROBE_SEEDS = range(900_001, 900_101)
STRIDE = 7


def sample_questions(suite: Suite, board: str, game: str, count: int) -> list[Question]:
    spec = suite.game(board, game)
    task = make_task(suite, board, game)
    reference = ReferencePlayer(game, spec.track, dict(spec.reference))
    found: list[Question] = []
    try:
        for seed in PROBE_SEEDS:
            task.reset(seed)
            reference.start(seed)
            index = 0
            while not task.done and len(found) < count:
                point = task.decision_point()
                rng = decision_rng(suite.id, f"probe-{board}", game, seed, index)
                question = point.question
                if len(question.options) > 1 and index % STRIDE == 0:
                    found.append(question.reordered(rng.shuffled(question.keys)[: suite.group_size]))
                task.apply(reference.decide(point, rng).choice)
                index += 1
            if len(found) >= count:
                break
    finally:
        task.close()
    return found


def smoke(suite: Suite, player: TextPlayer) -> Iterator[tuple[str, str, Call | PlayerError]]:
    """One probe question per game of every turn-based board, asked the way an episode asks: the answer, or
    the error that stopped it."""
    for board, game in suite.pairs():
        if suite.board(board).step_ms is not None:
            continue
        question = sample_questions(suite, board, game, 1)[0]
        try:
            yield board, game, player.ask(question, "smoke")
        except PlayerError as error:
            yield board, game, error
