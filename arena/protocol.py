"""How a question reaches a text player: a seeded option order, and a knockout when there are too many options.

The engine lists options in a canonical order that often carries meaning (columns left to right, placements by
rotation). Showing that order would hand any position bias a systematic edge, so every request shows a seeded
shuffle instead. When a question has more options than `group_size`, the shuffled options are split into balanced
groups, the player picks one per group, and a final (again shuffled) picks among the group winners; this repeats
until one request suffices. Every player goes through exactly the same procedure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from arena.core import Call, Decision, Question
from arena.seeding import Rng

type Ask = Callable[[Question, str], Call]


def split_groups(keys: Sequence[str], size: int) -> list[list[str]]:
    """Fewest groups of at most `size`, with sizes differing by at most one (larger groups first)."""
    if size < 2:
        raise ValueError("group size must be at least 2")
    count = -(-len(keys) // size)
    base, extra = divmod(len(keys), count)
    groups, start = [], 0
    for i in range(count):
        end = start + base + (1 if i < extra else 0)
        groups.append(list(keys[start:end]))
        start = end
    return groups


def decide(question: Question, ask: Ask, rng: Rng, group_size: int) -> Decision:
    """Ask `question` through `ask`, in a seeded order, with a knockout above `group_size` options."""
    keys = rng.shuffled(question.keys)
    calls: list[Call] = []
    round_number = 1
    while len(keys) > group_size:
        groups = split_groups(keys, group_size)
        winners = []
        for index, group in enumerate(groups, 1):
            call = ask(question.reordered(group), f"round {round_number} group {index}/{len(groups)}")
            calls.append(call)
            winners.append(call.choice)
        keys = rng.shuffled(winners)
        round_number += 1
    final = ask(question.reordered(keys), "final" if calls else "single")
    calls.append(final)
    return Decision(final.choice, tuple(calls))


def requests_needed(option_count: int, group_size: int) -> int:
    """How many requests `decide` makes for a question with `option_count` options."""
    total, count = 0, option_count
    while count > group_size:
        groups = -(-count // group_size)
        total += groups
        count = groups
    return total + 1
