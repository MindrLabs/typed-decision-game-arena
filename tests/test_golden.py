"""What models read, pinned: the first question of the first dev seed of every board and game.

A diff here means the text models see has changed. Before a suite is frozen that may be intended: regenerate with
`UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py` and review the diff. After freezing it means a new version.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arena.suite import Suite, load_suite
from arena.tasks import make_task

GOLDEN = Path(__file__).parent / "golden"
SUITE = load_suite("v0.1")
PAIRS = [(b, g) for b, g in SUITE.pairs() if SUITE.board(b).step_ms is None]


def render(suite: Suite, board: str, game: str) -> str:
    task = make_task(suite, board, game)
    seed = suite.game(board, game).seeds["dev"][0]
    task.reset(seed)
    q = task.decision_point().question
    task.close()
    options = "\n".join(f"[{o.key}] {o.text}" for o in q.options)
    return f"{q.state}\n\n--- instructions ---\n{q.instructions}\n\n--- options ---\n{options}\n"


@pytest.mark.parametrize(("board", "game"), PAIRS, ids=[f"{b}-{g}" for b, g in PAIRS])
def test_first_question(board: str, game: str) -> None:
    path = GOLDEN / f"{board}-{game}.txt"
    text = render(SUITE, board, game)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text)
    assert path.read_text() == text
