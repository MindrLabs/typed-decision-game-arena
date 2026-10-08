from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from arena.games import connect4 as C
from arena.seeding import Rng


def naive_winner(grid: list[str]) -> str | None:
    """Four in a row on a top-to-bottom grid of 'X'/'O'/'.'."""
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            mark = grid[r][c]
            if mark == ".":
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + k * dr, c + k * dc) for k in range(4)]
                if all(0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] == mark for rr, cc in cells):
                    return mark
    return None


@settings(max_examples=300, deadline=None)
@given(st.lists(st.integers(0, 6), min_size=0, max_size=42))
def test_bitboard_win_detection_matches_a_naive_check(moves: list[int]) -> None:
    board = C.Board()
    for col in moves:
        if board.winner() is not None or col not in board.legal():
            break
        board.play(col)
    expected = naive_winner(board.grid())
    winner = board.winner()
    assert (None if winner is None else "XO"[winner]) == expected


def test_seeds_cover_every_opponent_and_colour() -> None:
    for start in (1, 1001, 57):
        setups = {C.seed_setup(seed) for seed in range(start, start + 6)}
        assert setups == {(opponent, first) for opponent in C.LADDER for first in (True, False)}


def test_move_facts() -> None:
    board = C.Board()
    for col in (0, 6, 1, 6, 2):  # X threatens column 4 (0-based 3); O to move
        board.play(col)
    assert board.to_move == 1
    facts = {col: C.move_facts(board, col) for col in board.legal()}
    assert facts[3] == ["takes the cell where the opponent could complete four"]
    assert "after it the opponent can complete four on their next move" in facts[5]
    board.play(5)  # O does not block
    assert C.move_facts(board, 3) == ["wins the game"]


def test_blunder_counters() -> None:
    task = C.Connect4Task()
    task.reset(2)  # win-block opponent, the player moves first
    assert task.opponent == "win-block"
    assert task.me == 0
    task.board = C.Board()
    for col in (0, 6, 1, 6, 2, 5):  # X can win at column 4 (0-based 3)
        task.board.play(col)
    task.apply("c5")
    assert task.missed_wins == 1


def test_reference_beats_random() -> None:
    def play(seed: int, reference: bool) -> float:
        task = C.Connect4Task()
        task.reset(seed)
        rng = Rng(seed)
        while not task.done:
            point = task.decision_point()
            key = C.reference_move(point.view, 5, rng) if reference else rng.choice(point.question.keys)
            task.apply(key)
        return task.score()

    seeds = range(1, 7)
    assert sum(play(s, True) for s in seeds) / 6 >= 0.75
    assert sum(play(s, False) for s in seeds) / 6 <= 0.5
