"""Tetris: a 10 x 20 well, SRS piece shapes, basic rotation (no wall kicks), a seeded 7-bag and one next piece.

Rows are stored top to bottom as 10-bit masks (bit c = column c filled). Everything the models read numbers rows
from the bottom (row 1) and columns from the left (column 1), so "height" and "row" agree.

Two tasks share the engine:

* `macro`: one decision per piece, choosing among every final position the piece can reach by rotating and
  shifting at spawn height and then hard-dropping. Each option states what the board looks like right after
  the piece lands (lines cleared, holes, stack height); nothing ranks or recommends.
* `frame`: one decision per step, choosing a key; the piece falls one row every `gravity` steps.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from arena.core import JSON, DecisionPoint, Metric, Option, Question
from arena.seeding import Rng

WIDTH = 10
HEIGHT = 20
FULL_ROW = (1 << WIDTH) - 1
KINDS = ("I", "O", "T", "S", "Z", "J", "L")
ROTATIONS = ("spawn", "cw", "180", "ccw")
SPAWN_COL = 3

type Cell = tuple[int, int]  # (row from top, column from left), both 0-based
type Rows = tuple[int, ...]

# SRS orientations as (row, col) offsets inside each piece's bounding box, rotation states 0, R, 2, L.
SHAPES: dict[str, tuple[tuple[Cell, ...], ...]] = {
    "I": (
        ((1, 0), (1, 1), (1, 2), (1, 3)),
        ((0, 2), (1, 2), (2, 2), (3, 2)),
        ((2, 0), (2, 1), (2, 2), (2, 3)),
        ((0, 1), (1, 1), (2, 1), (3, 1)),
    ),
    "O": tuple(((0, 1), (0, 2), (1, 1), (1, 2)) for _ in range(4)),
    "T": (
        ((0, 1), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (1, 1), (1, 2), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 1)),
        ((0, 1), (1, 0), (1, 1), (2, 1)),
    ),
    "S": (
        ((0, 1), (0, 2), (1, 0), (1, 1)),
        ((0, 1), (1, 1), (1, 2), (2, 2)),
        ((1, 1), (1, 2), (2, 0), (2, 1)),
        ((0, 0), (1, 0), (1, 1), (2, 1)),
    ),
    "Z": (
        ((0, 0), (0, 1), (1, 1), (1, 2)),
        ((0, 2), (1, 1), (1, 2), (2, 1)),
        ((1, 0), (1, 1), (2, 1), (2, 2)),
        ((0, 1), (1, 0), (1, 1), (2, 0)),
    ),
    "J": (
        ((0, 0), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (0, 2), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 2)),
        ((0, 1), (1, 1), (2, 0), (2, 1)),
    ),
    "L": (
        ((0, 2), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (1, 1), (2, 1), (2, 2)),
        ((1, 0), (1, 1), (1, 2), (2, 0)),
        ((0, 0), (0, 1), (1, 1), (2, 1)),
    ),
}

EMPTY_BOARD: Rows = (0,) * HEIGHT


# --- board geometry ----------------------------------------------------------------------------------


def piece_cells(kind: str, rot: int, row: int, col: int) -> tuple[Cell, ...]:
    return tuple((row + dr, col + dc) for dr, dc in SHAPES[kind][rot])


def fits(rows: Rows, cells: tuple[Cell, ...]) -> bool:
    return all(0 <= r < HEIGHT and 0 <= c < WIDTH and not (rows[r] >> c) & 1 for r, c in cells)


def lock(rows: Rows, cells: tuple[Cell, ...]) -> tuple[Rows, int]:
    """Write the cells into the board and clear full rows. Returns the new board and lines cleared."""
    grid = list(rows)
    for r, c in cells:
        grid[r] |= 1 << c
    kept = [row for row in grid if row != FULL_ROW]
    cleared = HEIGHT - len(kept)
    return (0,) * cleared + tuple(kept), cleared


def column_heights(rows: Rows) -> list[int]:
    heights = [0] * WIDTH
    for c in range(WIDTH):
        for r in range(HEIGHT):
            if (rows[r] >> c) & 1:
                heights[c] = HEIGHT - r
                break
    return heights


def stack_height(rows: Rows) -> int:
    for r in range(HEIGHT):
        if rows[r]:
            return HEIGHT - r
    return 0


def holes(rows: Rows) -> int:
    """Empty cells with a filled cell somewhere above them in the same column."""
    count = 0
    covered = 0
    for row in rows:
        count += bin(covered & ~row & FULL_ROW).count("1")
        covered |= row
    return count


# --- features for the reference player (Dellacherie features, El-Tetris weights) --------------------


def row_transitions(rows: Rows) -> int:
    total = 0
    for row in rows:
        previous = 1  # the left wall counts as filled
        for c in range(WIDTH):
            bit = (row >> c) & 1
            total += bit != previous
            previous = bit
        total += previous != 1  # right wall
    return total


def column_transitions(rows: Rows) -> int:
    total = 0
    for c in range(WIDTH):
        previous = 0  # open sky above the well
        for r in range(HEIGHT):
            bit = (rows[r] >> c) & 1
            total += bit != previous
            previous = bit
        total += previous != 1  # the floor counts as filled
    return total


def well_sums(rows: Rows) -> int:
    total = 0
    for c in range(WIDTH):
        depth = 0
        for r in range(HEIGHT):
            row = rows[r]
            empty = not (row >> c) & 1
            left = c == 0 or (row >> (c - 1)) & 1
            right = c == WIDTH - 1 or (row >> (c + 1)) & 1
            if empty and left and right:
                depth += 1
                total += depth
            else:
                depth = 0
    return total


# --- placements ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Placement:
    """A final resting position of the current piece and the board right after it lands."""

    key: str
    rot: int
    col: int
    row: int
    cells: tuple[Cell, ...]
    board_after: Rows
    lines: int

    @property
    def columns(self) -> tuple[int, int]:
        cols = [c for _, c in self.cells]
        return min(cols) + 1, max(cols) + 1

    @property
    def rows_from_bottom(self) -> tuple[int, int]:
        rs = [HEIGHT - r for r, _ in self.cells]
        return min(rs), max(rs)

    @property
    def holes_after(self) -> int:
        return holes(self.board_after)

    @property
    def height_after(self) -> int:
        return stack_height(self.board_after)


def land(rows: Rows, kind: str, rot: int, row: int, col: int) -> Placement:
    """The placement of a piece resting at (rot, row, col)."""
    cells = piece_cells(kind, rot, row, col)
    board_after, lines = lock(rows, cells)
    left = min(c for _, c in cells) + 1
    return Placement(f"{ROTATIONS[rot]}-c{left}", rot, col, row, cells, board_after, lines)


def drop_row(rows: Rows, kind: str, rot: int, row: int, col: int) -> int:
    while fits(rows, piece_cells(kind, rot, row + 1, col)):
        row += 1
    return row


def reachable_at_row(rows: Rows, kind: str, rot: int, row: int, col: int) -> list[tuple[int, int]]:
    """(rotation, column) pairs reachable from (rot, col) by shifting and rotating without leaving `row`,
    in breadth-first order."""
    start = (rot, col)
    seen = {start}
    order = [start]
    queue = deque([start])
    while queue:
        r0, c0 = queue.popleft()
        for r1, c1 in ((r0, c0 - 1), (r0, c0 + 1), ((r0 + 1) % 4, c0), ((r0 + 3) % 4, c0)):
            if (r1, c1) not in seen and fits(rows, piece_cells(kind, r1, row, c1)):
                seen.add((r1, c1))
                order.append((r1, c1))
                queue.append((r1, c1))
    return order


def placements(rows: Rows, kind: str, rot: int, row: int, col: int) -> list[Placement]:
    """Every distinct landing reachable from the given position by rotate/shift then hard drop,
    in canonical order (rotation spawn, cw, 180, ccw; then leftmost column). Placements that cover the same
    cells are one option, kept under the first rotation that reaches them."""
    reach = sorted(reachable_at_row(rows, kind, rot, row, col))
    found: dict[frozenset[Cell], Placement] = {}
    for r1, c1 in reach:
        placement = land(rows, kind, r1, drop_row(rows, kind, r1, row, c1), c1)
        found.setdefault(frozenset(placement.cells), placement)
    return list(found.values())


# --- engine -------------------------------------------------------------------------------------------


class Bag:
    """The seeded 7-bag stream. The piece sequence depends on the seed only, never on play."""

    def __init__(self, seed: int) -> None:
        self._rng = Rng.derive("tetris", "bag", seed)
        self._queue: deque[str] = deque()

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        if not self._queue:
            self._queue.extend(self._rng.shuffled(KINDS))
        return self._queue.popleft()


@dataclass
class Active:
    kind: str
    rot: int
    row: int
    col: int

    def cells(self) -> tuple[Cell, ...]:
        return piece_cells(self.kind, self.rot, self.row, self.col)


@dataclass
class Tetris:
    seed: int
    gravity: int = 2
    rows: Rows = EMPTY_BOARD
    lines: int = 0
    pieces: int = 0
    steps: int = 0
    over: bool = False
    gravity_timer: int = 0
    bag: Bag = field(init=False)
    piece: Active = field(init=False)
    next_kind: str = field(init=False)

    def __post_init__(self) -> None:
        self.bag = Bag(self.seed)
        self.next_kind = next(self.bag)
        self._spawn()

    def _spawn(self) -> None:
        self.piece = Active(self.next_kind, 0, 0, SPAWN_COL)
        self.next_kind = next(self.bag)
        self.gravity_timer = 0
        if not fits(self.rows, self.piece.cells()):
            self.over = True  # block out

    def _lock(self, cells: tuple[Cell, ...]) -> int:
        self.rows, cleared = lock(self.rows, cells)
        self.lines += cleared
        self.pieces += 1
        self._spawn()
        return cleared

    def placements(self) -> list[Placement]:
        p = self.piece
        return placements(self.rows, p.kind, p.rot, p.row, p.col)

    def place(self, placement: Placement) -> None:
        """Macro move: put the piece at a placement from `placements()`."""
        self.steps += 1
        self._lock(placement.cells)

    def _try(self, rot: int, row: int, col: int) -> bool:
        cells = piece_cells(self.piece.kind, rot, row, col)
        if fits(self.rows, cells):
            self.piece.rot, self.piece.row, self.piece.col = rot, row, col
            return True
        return False

    def can(self, key: str) -> bool:
        p = self.piece
        moves = {
            "left": (p.rot, p.row, p.col - 1),
            "right": (p.rot, p.row, p.col + 1),
            "cw": ((p.rot + 1) % 4, p.row, p.col),
            "ccw": ((p.rot + 3) % 4, p.row, p.col),
        }
        if key in moves:
            return fits(self.rows, piece_cells(p.kind, *moves[key]))
        return key in FRAME_KEYS

    def step(self, key: str) -> None:
        """Frame move: one key, then gravity. An illegal key does nothing."""
        p = self.piece
        self.steps += 1
        if key == "left":
            self._try(p.rot, p.row, p.col - 1)
        elif key == "right":
            self._try(p.rot, p.row, p.col + 1)
        elif key == "cw":
            self._try((p.rot + 1) % 4, p.row, p.col)
        elif key == "ccw":
            self._try((p.rot + 3) % 4, p.row, p.col)
        elif key == "soft":
            if not self._try(p.rot, p.row + 1, p.col):
                self._lock(p.cells())
                return
        elif key == "hard":
            self._lock(piece_cells(p.kind, p.rot, drop_row(self.rows, p.kind, p.rot, p.row, p.col), p.col))
            return
        self.gravity_timer += 1
        if self.gravity_timer >= self.gravity:
            self.gravity_timer = 0
            if not self._try(p.rot, p.row + 1, p.col):
                self._lock(p.cells())

    def snapshot(self) -> JSON:
        return {
            "board": board_strings(self.rows),
            "piece": {"kind": self.piece.kind, "cells": [list(cell) for cell in self.piece.cells()]},
            "next": self.next_kind,
            "lines": self.lines,
            "pieces": self.pieces,
            "over": self.over,
        }


def board_strings(rows: Rows) -> list[str]:
    """Top to bottom, '#' filled and '.' empty."""
    return ["".join("#" if (row >> c) & 1 else "." for c in range(WIDTH)) for row in rows]


# --- text ---------------------------------------------------------------------------------------------

FRAME_KEYS = ("left", "right", "cw", "ccw", "soft", "hard", "wait")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _span(word: str, low: int, high: int) -> str:
    """'column 4' or 'columns 4-6'."""
    return f"{word} {low}" if low == high else f"{word}s {low}-{high}"


def render_board(rows: Rows, active: tuple[Cell, ...] = ()) -> str:
    """Rows from 20 down to 1; each run of empty rows is one line, so the text stays short and lossless.
    '#' is a filled cell, '.' an empty one and '@' the falling piece."""
    marks = set(active)
    if not any(rows) and not marks:
        return "The well is empty."
    lines: list[str] = []
    run: list[int] = []

    def flush() -> None:
        if run:
            lines.append(f"Row {run[0]} is empty." if len(run) == 1 else f"Rows {run[0]}-{run[-1]} are empty.")
            run.clear()

    for r in range(HEIGHT):
        number = HEIGHT - r
        if not rows[r] and not any(mr == r for mr, _ in marks):
            run.append(number)
            continue
        flush()
        cells = "".join("@" if (r, c) in marks else ("#" if (rows[r] >> c) & 1 else ".") for c in range(WIDTH))
        lines.append(f"{number:>2} {cells}")
    flush()
    return "\n".join(lines)


def _state_header(game: Tetris) -> list[str]:
    return [
        "Tetris. The well is 10 columns wide (column 1 on the left) and 20 rows tall (row 1 at the bottom). "
        "A full row clears; the game ends when a new piece has no room at the top.",
        f"Current piece: {game.piece.kind}. Next piece: {game.next_kind}.",
        f"Lines cleared: {game.lines}. Pieces placed: {game.pieces}. "
        f"Stack height: {stack_height(game.rows)}. Holes: {holes(game.rows)}.",
    ]


def landing_text(placement: Placement) -> str:
    where = f"{_span('column', *placement.columns)}, {_span('row', *placement.rows_from_bottom)}"
    return (
        f"lands in {where}: clears {_plural(placement.lines, 'line')}; "
        f"holes after: {placement.holes_after}; stack height after: {placement.height_after}"
    )


def placement_text(placement: Placement) -> str:
    return f"rotation {ROTATIONS[placement.rot]}, {landing_text(placement)}"


MACRO_INSTRUCTIONS = (
    "Choose where the current piece lands. Each option is a final position (rotation, columns and rows) and the "
    "board right after it lands. Goal: clear as many lines as possible before the stack reaches the top."
)

FRAME_INSTRUCTIONS = (
    "Choose the key for this step. The piece falls one row on its own every {gravity} steps and locks when it "
    "cannot fall. Goal: clear as many lines as possible before the stack reaches the top."
)


@dataclass(frozen=True, slots=True)
class MacroView:
    rows: Rows
    kind: str
    next_kind: str
    placements: tuple[Placement, ...]


@dataclass(frozen=True, slots=True)
class FrameView:
    game: Tetris


class TetrisMacro:
    game = "tetris"
    track = "macro"
    default_key = ""

    def __init__(self, piece_cap: int = 300) -> None:
        self.piece_cap = piece_cap
        self.state = Tetris(seed=0)
        self._options: dict[str, Placement] = {}

    def reset(self, seed: int) -> None:
        self.state = Tetris(seed=seed)
        self._options = {}

    @property
    def done(self) -> bool:
        return self.state.over or self.state.pieces >= self.piece_cap

    @property
    def steps(self) -> int:
        return self.state.steps

    def decision_point(self) -> DecisionPoint:
        found = self.state.placements()
        self._options = {p.key: p for p in found}
        state = "\n".join([*_state_header(self.state), render_board(self.state.rows)])
        question = Question(state, MACRO_INSTRUCTIONS, tuple(Option(p.key, placement_text(p)) for p in found))
        view = MacroView(self.state.rows, self.state.piece.kind, self.state.next_kind, tuple(found))
        return DecisionPoint(question, view)

    def apply(self, key: str) -> None:
        if key not in self._options:
            self._options = {p.key: p for p in self.state.placements()}
        if key not in self._options:
            raise ValueError(f"no placement {key!r}; legal: {sorted(self._options)}")
        self.state.place(self._options[key])
        self._options = {}

    def held(self, key: str) -> str:
        return key

    def score(self) -> float:
        return float(self.state.lines)

    def metrics(self) -> dict[str, Metric]:
        return {"lines": self.state.lines, "pieces": self.state.pieces, "topped_out": self.state.over}

    def snapshot(self) -> JSON:
        """The position, plus the cells of every landing on offer (keyed like the options) while a decision is
        open, so a replay can draw where the chosen piece came to rest."""
        snap = self.state.snapshot()
        if self._options:
            snap["landings"] = {key: [list(cell) for cell in p.cells] for key, p in self._options.items()}
        return snap

    def close(self) -> None:
        pass


FRAME_TEXT = {
    "left": "move the piece one column left",
    "right": "move the piece one column right",
    "cw": "rotate the piece clockwise",
    "ccw": "rotate the piece counter-clockwise",
    "soft": "move the piece down one row",
    "wait": "do nothing this step",
}


class TetrisFrame:
    game = "tetris"
    track = "frame"
    default_key = "wait"

    def __init__(self, piece_cap: int = 100, gravity: int = 2) -> None:
        self.piece_cap = piece_cap
        self.gravity = gravity
        self.state = Tetris(seed=0, gravity=gravity)

    def reset(self, seed: int) -> None:
        self.state = Tetris(seed=seed, gravity=self.gravity)

    @property
    def done(self) -> bool:
        return self.state.over or self.state.pieces >= self.piece_cap

    @property
    def steps(self) -> int:
        return self.state.steps

    def _key_text(self, key: str) -> str:
        s, p = self.state, self.state.piece
        if key == "hard":
            row = drop_row(s.rows, p.kind, p.rot, p.row, p.col)
            return "drop the piece now; it " + landing_text(land(s.rows, p.kind, p.rot, row, p.col))
        if key == "soft" and not fits(s.rows, piece_cells(p.kind, p.rot, p.row + 1, p.col)):
            return "lock the piece where it is; it " + landing_text(land(s.rows, p.kind, p.rot, p.row, p.col))
        return FRAME_TEXT[key]

    def decision_point(self) -> DecisionPoint:
        s = self.state
        keys = [key for key in FRAME_KEYS if s.can(key)]
        p = s.piece
        low = min(HEIGHT - r for r, _ in p.cells())
        cols = [c + 1 for _, c in p.cells()]
        falls_in = s.gravity - s.gravity_timer
        state = "\n".join(
            [
                *_state_header(s),
                f"The {p.kind} piece is at rotation {ROTATIONS[p.rot]}, {_span('column', min(cols), max(cols))}, "
                f"lowest cell in row {low}; it falls one row in {_plural(falls_in, 'step')}. '@' marks it below.",
                render_board(s.rows, p.cells()),
            ]
        )
        question = Question(
            state,
            FRAME_INSTRUCTIONS.format(gravity=s.gravity),
            tuple(Option(key, self._key_text(key)) for key in keys),
        )
        return DecisionPoint(question, FrameView(s))

    def apply(self, key: str) -> None:
        self.state.step(key)

    def held(self, key: str) -> str:
        return "wait"  # a key press acts once

    def score(self) -> float:
        return float(self.state.lines)

    def metrics(self) -> dict[str, Metric]:
        return {"lines": self.state.lines, "pieces": self.state.pieces, "topped_out": self.state.over}

    def snapshot(self) -> JSON:
        return self.state.snapshot()

    def close(self) -> None:
        pass


# --- reference player: Dellacherie's features with El-Tetris weights (El-Ashi 2011) -----------------------

EL_TETRIS = (
    -4.500158825082766,  # landing height
    3.4181268101392694,  # eroded piece cells
    -3.2178882868487753,  # row transitions
    -9.348695305445199,  # column transitions
    -7.899265427351652,  # holes
    -3.3855972247263626,  # well sums
)


def placement_value(rows: Rows, placement: Placement) -> float:
    low, high = placement.rows_from_bottom
    grid = list(rows)
    for r, c in placement.cells:
        grid[r] |= 1 << c
    full = {r for r, row in enumerate(grid) if row == FULL_ROW}
    eroded = len(full) * sum(1 for r, _ in placement.cells if r in full)
    after = placement.board_after
    w = EL_TETRIS
    return (
        w[0] * (low + high) / 2
        + w[1] * eroded
        + w[2] * row_transitions(after)
        + w[3] * column_transitions(after)
        + w[4] * holes(after)
        + w[5] * well_sums(after)
    )


def best_placement(rows: Rows, found: list[Placement] | tuple[Placement, ...]) -> Placement:
    """Highest value; ties keep the canonical order."""
    best = found[0]
    best_value = placement_value(rows, best)
    for placement in found[1:]:
        value = placement_value(rows, placement)
        if value > best_value:
            best, best_value = placement, value
    return best


def reference_macro(view: MacroView) -> str:
    return best_placement(view.rows, view.placements).key


class FramePlanner:
    """Frame-track reference: pick the best placement for the current piece, then rotate, shift and hard-drop
    towards it, re-planning whenever a move is blocked."""

    def __init__(self) -> None:
        self._piece = -1
        self._target: tuple[int, int] | None = None

    def start(self) -> None:
        self._piece = -1
        self._target = None

    def __call__(self, view: FrameView) -> str:
        game = view.game
        p = game.piece
        if self._piece != game.pieces or self._target is None:
            self._plan(game)
        assert self._target is not None
        rot, col = self._target
        if p.rot != rot:
            key = "cw" if (rot - p.rot) % 4 in (1, 2) else "ccw"
        elif p.col != col:
            key = "right" if p.col < col else "left"
        else:
            return "hard"
        if game.can(key):
            return key
        self._plan(game)
        return "hard" if self._target == (p.rot, p.col) else ("wait" if game.can("wait") else "hard")

    def _plan(self, game: Tetris) -> None:
        p = game.piece
        found = placements(game.rows, p.kind, p.rot, p.row, p.col)
        best = best_placement(game.rows, found)
        self._piece = game.pieces
        self._target = (best.rot, best.col)
