"""Snake on a 10 x 10 grid. The snake starts with length 3 heading up; each step it turns left, goes straight
or turns right. Eating food grows it by one; hitting a wall or its own body ends the game.

Food #k is the first empty cell in a stream seeded by (seed, k), so every player meets the same food sequence
unless the snake happens to cover a cell. An episode also ends after `step_cap` steps, or after `starve_cap`
steps without food (circling forever is not a strategy the score should reward with more time).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from arena.core import JSON, DecisionPoint, Metric, Option, Question
from arena.seeding import Rng

SIZE = 10
HEADINGS = ("up", "right", "down", "left")
COMPASS = ("north", "east", "south", "west")
DELTAS = ((-1, 0), (0, 1), (1, 0), (0, -1))
MOVES = ("left", "straight", "right")
TURN = {"left": 3, "straight": 0, "right": 1}

type Cell = tuple[int, int]  # (row from top, column from left), 0-based


@dataclass
class Snake:
    seed: int
    body: deque[Cell] = field(default_factory=lambda: deque([(4, 4), (5, 4), (6, 4)]))  # head first
    heading: int = 0
    food: Cell | None = None
    eaten: int = 0
    steps: int = 0
    since_food: int = 0
    alive: bool = True
    death: str = ""

    def __post_init__(self) -> None:
        self._place_food()

    def _place_food(self) -> None:
        occupied = set(self.body)
        if len(occupied) == SIZE * SIZE:
            self.food = None
            return
        rng = Rng.derive("snake", "food", self.seed, self.eaten)
        while True:
            cell = (rng.below(SIZE), rng.below(SIZE))
            if cell not in occupied:
                self.food = cell
                return

    @property
    def head(self) -> Cell:
        return self.body[0]

    def target(self, move: str) -> tuple[int, Cell]:
        heading = (self.heading + TURN[move]) % 4
        dr, dc = DELTAS[heading]
        return heading, (self.head[0] + dr, self.head[1] + dc)

    def outcome(self, move: str) -> str:
        """'wall', 'body', 'food' or 'empty' for the cell the head would enter."""
        _, (r, c) = self.target(move)
        if not (0 <= r < SIZE and 0 <= c < SIZE):
            return "wall"
        eats = (r, c) == self.food
        # The tail moves away this step unless the snake grows.
        blocking = list(self.body) if eats else list(self.body)[:-1]
        if (r, c) in blocking:
            return "body"
        return "food" if eats else "empty"

    def step(self, move: str) -> None:
        result = self.outcome(move)
        heading, cell = self.target(move)
        self.steps += 1
        self.heading = heading
        if result in ("wall", "body"):
            self.alive = False
            self.death = result
            return
        self.body.appendleft(cell)
        if result == "food":
            self.eaten += 1
            self.since_food = 0
            self._place_food()
        else:
            self.body.pop()
            self.since_food += 1

    def copy(self) -> Snake:
        clone = Snake.__new__(Snake)
        clone.seed, clone.body, clone.heading, clone.food = self.seed, deque(self.body), self.heading, self.food
        clone.eaten, clone.steps, clone.since_food = self.eaten, self.steps, self.since_food
        clone.alive, clone.death = self.alive, self.death
        return clone

    def snapshot(self) -> JSON:
        return {
            "size": SIZE,
            "snake": [list(cell) for cell in self.body],
            "food": list(self.food) if self.food else None,
            "heading": HEADINGS[self.heading],
            "eaten": self.eaten,
            "alive": self.alive,
        }


# --- text ---------------------------------------------------------------------------------------------

INSTRUCTIONS = (
    "Choose the snake's move for this step. Each option names the turn, the cell the head enters and what "
    "happens there. Goal: eat as much food as possible without hitting a wall or the snake's own body."
)

OUTCOME_TEXT = {
    "body": "the snake's body is there, so the game ends",
    "food": "the snake eats the food there",
    "empty": "the cell is empty",
}

MOVE_TEXT = {"left": "turn left", "straight": "go straight", "right": "turn right"}


def _cell(cell: Cell) -> str:
    return f"row {cell[0] + 1}, column {cell[1] + 1}"


def render_grid(game: Snake) -> str:
    marks: dict[Cell, str] = {cell: "o" for cell in game.body}
    marks[game.body[-1]] = "t"
    marks[game.head] = "H"
    if game.food:
        marks[game.food] = "*"
    return "\n".join(f"{r + 1:>2} " + " ".join(marks.get((r, c), ".") for c in range(SIZE)) for r in range(SIZE))


def render_state(game: Snake) -> str:
    food = _cell(game.food) if game.food else "none (the grid is full)"
    return "\n".join(
        [
            "Snake on a 10 x 10 grid (row 1 at the top, column 1 on the left). The snake moves one cell per step; "
            "eating food makes it one cell longer. Hitting a wall or its own body ends the game.",
            f"Heading: {HEADINGS[game.heading]}. Length: {len(game.body)}. Food eaten: {game.eaten}. "
            f"Steps since the last food: {game.since_food}.",
            f"Head at {_cell(game.head)}. Tail at {_cell(game.body[-1])}. Food at {food}.",
            "Grid (H head, o body, t tail, * food, . empty):",
            render_grid(game),
        ]
    )


def option_text(game: Snake, move: str) -> str:
    heading, cell = game.target(move)
    outcome = game.outcome(move)
    if outcome == "wall":
        return f"{MOVE_TEXT[move]}: the head would leave the grid to the {COMPASS[heading]}, so the game ends"
    return f"{MOVE_TEXT[move]}: the head moves {COMPASS[heading]} to {_cell(cell)}; {OUTCOME_TEXT[outcome]}"


@dataclass(frozen=True, slots=True)
class SnakeView:
    game: Snake


class SnakeTask:
    game = "snake"
    track = "macro"
    default_key = "straight"

    def __init__(self, step_cap: int = 1000, starve_cap: int = 200) -> None:
        self.step_cap = step_cap
        self.starve_cap = starve_cap
        self.state = Snake(seed=0)

    def reset(self, seed: int) -> None:
        self.state = Snake(seed=seed)

    @property
    def done(self) -> bool:
        s = self.state
        return not s.alive or s.food is None or s.steps >= self.step_cap or s.since_food >= self.starve_cap

    @property
    def steps(self) -> int:
        return self.state.steps

    def decision_point(self) -> DecisionPoint:
        question = Question(
            render_state(self.state),
            INSTRUCTIONS,
            tuple(Option(move, option_text(self.state, move)) for move in MOVES),
        )
        return DecisionPoint(question, SnakeView(self.state.copy()))

    def apply(self, key: str) -> None:
        if key not in TURN:
            raise ValueError(f"unknown snake move {key!r}")
        self.state.step(key)

    def held(self, key: str) -> str:
        return key

    def score(self) -> float:
        return float(self.state.eaten)

    def metrics(self) -> dict[str, Metric]:
        s = self.state
        return {
            "food": s.eaten,
            "length": len(s.body),
            "died": not s.alive,
            "death": s.death or "none",
            "starved": s.alive and s.since_food >= self.starve_cap,
        }

    def snapshot(self) -> JSON:
        return self.state.snapshot()

    def close(self) -> None:
        pass


# --- reference player -----------------------------------------------------------------------------------


def _neighbours(cell: Cell) -> list[Cell]:
    r, c = cell
    return [(r + dr, c + dc) for dr, dc in DELTAS if 0 <= r + dr < SIZE and 0 <= c + dc < SIZE]


def _path(start: Cell, goal: Cell, blocked: set[Cell]) -> list[Cell] | None:
    """Shortest path from start to goal (excluding start), avoiding blocked cells; deterministic order."""
    previous: dict[Cell, Cell] = {start: start}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = [cell]
            while previous[path[-1]] != start:
                path.append(previous[path[-1]])
            return path[::-1]
        for nxt in _neighbours(cell):
            if nxt not in previous and (nxt == goal or nxt not in blocked):
                previous[nxt] = cell
                queue.append(nxt)
    return None


def _tail_reachable(game: Snake) -> bool:
    body = list(game.body)
    if len(body) < 2:
        return True
    return _path(body[0], body[-1], set(body[1:-1])) is not None


def _area(game: Snake) -> int:
    blocked = set(list(game.body)[:-1])
    seen = {game.head}
    queue = deque([game.head])
    while queue:
        for nxt in _neighbours(queue.popleft()):
            if nxt not in seen and nxt not in blocked:
                seen.add(nxt)
                queue.append(nxt)
    return len(seen)


def _move_towards(game: Snake, cell: Cell) -> str | None:
    for move in MOVES:
        if game.target(move)[1] == cell:
            return move
    return None


def reference_move(game: Snake) -> str:
    """Shortest path to the food when the snake can still reach its tail after eating; otherwise the safe move
    that keeps the tail reachable and stays farthest from the food; otherwise the move with the most room."""
    safe = [move for move in MOVES if game.outcome(move) in ("food", "empty")]
    if not safe:
        return "straight"
    if game.food is not None:
        path = _path(game.head, game.food, set(list(game.body)[:-1]))
        if path:
            ghost = game.copy()
            for cell in path:
                move = _move_towards(ghost, cell)
                if move is None or ghost.outcome(move) in ("wall", "body"):
                    break
                ghost.step(move)
            else:
                first = _move_towards(game, path[0])
                if first in safe and _tail_reachable(ghost):
                    return first
    keeping: list[tuple[int, str]] = []
    for move in safe:
        ghost = game.copy()
        ghost.step(move)
        if _tail_reachable(ghost):
            distance = abs(ghost.head[0] - game.food[0]) + abs(ghost.head[1] - game.food[1]) if game.food else 0
            keeping.append((distance, move))
    if keeping:
        return max(keeping, key=lambda item: (item[0], -MOVES.index(item[1])))[1]
    rooms = []
    for move in safe:
        ghost = game.copy()
        ghost.step(move)
        rooms.append((_area(ghost), move))
    return max(rooms, key=lambda item: (item[0], -MOVES.index(item[1])))[1]
