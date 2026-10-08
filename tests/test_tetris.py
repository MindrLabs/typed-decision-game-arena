from __future__ import annotations

import pytest

from arena.games import tetris as T
from arena.seeding import Rng


def rows_from(picture: list[str]) -> T.Rows:
    """Bottom rows of a board from strings (top to bottom), padded with empty rows above."""
    rows = [sum(1 << c for c, ch in enumerate(line) if ch == "#") for line in picture]
    return (0,) * (T.HEIGHT - len(rows)) + tuple(rows)


def test_shapes_have_four_cells_in_every_rotation() -> None:
    for kind, rotations in T.SHAPES.items():
        assert len(rotations) == 4, kind
        assert all(len(set(cells)) == 4 for cells in rotations), kind


@pytest.mark.parametrize(
    ("kind", "count"), [("I", 17), ("O", 9), ("T", 34), ("S", 17), ("Z", 17), ("J", 34), ("L", 34)]
)
def test_placements_on_an_empty_board(kind: str, count: int) -> None:
    found = T.placements(T.EMPTY_BOARD, kind, 0, 0, T.SPAWN_COL)
    assert len(found) == count
    assert len({frozenset(p.cells) for p in found}) == count  # distinct footprints
    assert len({p.key for p in found}) == count  # distinct keys
    for p in found:
        below = tuple((r + 1, c) for r, c in p.cells)
        assert not T.fits(T.EMPTY_BOARD, below)  # every placement rests


def test_lock_clears_full_rows_and_counts() -> None:
    rows = rows_from(["#########.", "#########."])
    i_vertical = T.piece_cells("I", 1, T.HEIGHT - 4, 7)  # column 9 (0-based), rows 16-19
    after, cleared = T.lock(rows, i_vertical)
    assert cleared == 2
    assert T.stack_height(after) == 2
    assert T.board_strings(after)[-2:] == [".........#", ".........#"]


def test_holes_and_height() -> None:
    rows = rows_from(["#.........", "..........", "##........"])
    assert T.holes(rows) == 1  # the cell under the top-left block
    assert T.stack_height(rows) == 3
    assert T.column_heights(rows)[:3] == [3, 1, 0]


def test_bag_gives_every_piece_once_per_seven() -> None:
    bag = T.Bag(11)
    pieces = [next(bag) for _ in range(70)]
    for start in range(0, 70, 7):
        assert sorted(pieces[start : start + 7]) == sorted(T.KINDS)
    assert pieces == [next(T.Bag(11)) for _ in range(1)] + pieces[1:]  # same seed, same sequence


def test_bag_does_not_depend_on_play() -> None:
    a, b = T.TetrisMacro(), T.TetrisMacro()
    a.reset(5)
    b.reset(5)
    seen_a, seen_b = [], []
    rng = Rng(1)
    for _ in range(20):
        seen_a.append(a.state.piece.kind)
        seen_b.append(b.state.piece.kind)
        a.apply(a.decision_point().question.options[0].key)
        b.apply(rng.choice(b.decision_point().question.keys))
        if a.done or b.done:
            break
    assert seen_a == seen_b


def test_macro_is_deterministic() -> None:
    def play() -> list[str]:
        task = T.TetrisMacro(piece_cap=40)
        task.reset(3)
        texts = []
        while not task.done:
            point = task.decision_point()
            texts.append(point.question.state)
            task.apply(T.reference_macro(point.view))
        return texts

    assert play() == play()


def test_frame_gravity_and_drops() -> None:
    task = T.TetrisFrame(piece_cap=5, gravity=2)
    task.reset(1)
    start_row = task.state.piece.row
    task.apply("wait")
    assert task.state.piece.row == start_row
    task.apply("wait")
    assert task.state.piece.row == start_row + 1  # one row every two steps
    pieces = task.state.pieces
    task.apply("hard")
    assert task.state.pieces == pieces + 1
    assert task.state.gravity_timer == 0


def test_frame_illegal_key_does_nothing() -> None:
    task = T.TetrisFrame()
    task.reset(1)
    for _ in range(10):
        task.apply("left")
    col = task.state.piece.col
    task.apply("left")  # against the wall: no movement
    assert task.state.piece.col == col
    assert "left" not in task.decision_point().question.keys


def test_board_text_elides_empty_rows() -> None:
    assert T.render_board(T.EMPTY_BOARD) == "The well is empty."
    text = T.render_board(rows_from(["#.........", ".........."]))
    assert text.splitlines() == ["Rows 20-3 are empty.", " 2 #.........", "Row 1 is empty."]


def test_reference_clears_lines_and_random_does_not() -> None:
    task = T.TetrisMacro(piece_cap=150)
    task.reset(1001)
    while not task.done:
        task.apply(T.reference_macro(task.decision_point().view))
    assert task.score() >= 55  # 150 pieces hold at most 60 lines

    rng = Rng(7)
    task.reset(1001)
    while not task.done:
        task.apply(rng.choice(task.decision_point().question.keys))
    assert task.score() <= 2


def test_frame_reference_follows_its_plan() -> None:
    planner = T.FramePlanner()
    task = T.TetrisFrame(piece_cap=30)
    task.reset(1001)
    planner.start()
    while not task.done:
        task.apply(planner(task.decision_point().view))
    assert task.score() >= 8  # 30 pieces hold at most 12 lines


def test_macro_snapshot_lists_every_landing_while_deciding() -> None:
    task = T.TetrisMacro()
    task.reset(1)
    point = task.decision_point()
    landings = task.snapshot()["landings"]
    assert list(landings) == list(point.question.keys)
    assert all(len(cells) == 4 for cells in landings.values())
    task.apply(point.question.keys[0])
    assert "landings" not in task.snapshot()  # no decision open between moves
