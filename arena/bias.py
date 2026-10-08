"""Position bias: ask the same question in one order and in the reverse order.

A player that reads the options picks the same option both times. One that leans on position picks the same
place instead. Reported per game and overall: agreement (same option in both orders), how often the first shown
option is picked against the rate a uniform pick would give, and the same for the last option.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from arena.client import DEFAULT_SERVER, ModelClient
from arena.core import JSON
from arena.logs import RESULTS, say, write_json
from arena.players import TextPlayer
from arena.probe import sample_questions
from arena.registry import contestants
from arena.suite import Suite, locked_digest


def bias_path(suite_id: str, player_id: str, results: Path = RESULTS) -> Path:
    return results / suite_id / "bias" / f"{player_id}.json"


def _summary(rows: list[tuple[int, int, int, bool]]) -> JSON:
    """rows: (option count, position picked in order A, position picked in reversed order B, same option)."""
    if not rows:
        return {"n": 0}
    n = len(rows)
    picks = 2 * n
    first = sum((a == 0) + (b == 0) for _, a, b, _ in rows)
    last = sum((a == count - 1) + (b == count - 1) for count, a, b, _ in rows)
    uniform = sum(2 / count for count, *_ in rows)
    return {
        "n": n,
        "agreement": round(sum(same for *_, same in rows) / n, 4),
        "first_rate": round(first / picks, 4),
        "last_rate": round(last / picks, 4),
        "uniform_rate": round(uniform / picks, 4),
    }


def measure(
    suite: Suite,
    player_id: str,
    *,
    server: str = DEFAULT_SERVER,
    sample: int = 40,
    results: Path = RESULTS,
    progress: Callable[[str], None] = say,
) -> Path:
    contestant = contestants()[player_id]
    player = TextPlayer(contestant, ModelClient(server), suite.group_size)
    games: dict[str, JSON] = {}
    everything: list[tuple[int, int, int, bool]] = []
    try:
        for board, game in suite.pairs():
            if board != "macro":
                continue
            rows = []
            for question in sample_questions(suite, board, game, sample):
                if len(question.options) < 3:
                    continue
                forward = player.ask(question, "bias forward")
                backward = player.ask(question.reordered(question.keys[::-1]), "bias reverse")
                count = len(question.options)
                rows.append(
                    (
                        count,
                        question.keys.index(forward.choice),
                        question.keys[::-1].index(backward.choice),
                        forward.choice == backward.choice,
                    )
                )
            games[game] = _summary(rows)
            everything.extend(rows)
            progress(f"{player_id} {game}: {games[game]}")
    finally:
        player.close()
    path = bias_path(suite.id, player_id, results)
    write_json(
        path,
        {
            "suite": suite.id,
            "lock": locked_digest(suite),
            "player": player_id,
            "measured": datetime.now(UTC).isoformat(timespec="seconds"),
            "games": games,
            "overall": _summary(everything),
        },
    )
    return path
