"""Connect Four on 7 columns x 6 rows against a fixed ladder of rule-based opponents.

The seed picks the opponent and the colour: seeds cycle through the ladder (random, win-or-block, negamax at
depth 4) and every block of three seeds swaps who moves first, so any 6k consecutive seeds give each
(opponent, colour) pair the same number of games. Only the player's own turns are decisions; opponent moves
are played inside `reset` and `apply`.

Each option states facts that hold right after the move: whether it wins, whether it occupies a cell where
the opponent could win at once, and whether it leaves the opponent an immediate win. Nothing looks further.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from arena.core import JSON, DecisionPoint, Metric, Option, Question
from arena.seeding import Rng

ROWS = 6
COLS = 7
STRIDE = ROWS + 1  # one sentinel bit on top of each column keeps shifts from wrapping
CENTER_ORDER = (3, 2, 4, 1, 5, 0, 6)
LADDER = ("random", "win-block", "negamax-4")
WIN_SCORE = 1_000_000


def bit(col: int, row: int) -> int:
    return 1 << (col * STRIDE + row)


def has_four(stones: int) -> bool:
    for shift in (1, STRIDE, STRIDE - 1, STRIDE + 1):  # vertical, horizontal, two diagonals
        pairs = stones & (stones >> shift)
        if pairs & (pairs >> (2 * shift)):
            return True
    return False


@cache
def _windows() -> tuple[int, ...]:
    """Every line of four cells as a mask."""
    found = []
    for col in range(COLS):
        for row in range(ROWS):
            for dc, dr in ((1, 0), (0, 1), (1, 1), (1, -1)):
                cells = [(col + k * dc, row + k * dr) for k in range(4)]
                if all(0 <= c < COLS and 0 <= r < ROWS for c, r in cells):
                    mask = 0
                    for c, r in cells:
                        mask |= bit(c, r)
                    found.append(mask)
    return tuple(found)


@dataclass
class Board:
    stones: list[int] = field(default_factory=lambda: [0, 0])  # index 0 moves first
    heights: list[int] = field(default_factory=lambda: [0] * COLS)
    history: list[int] = field(default_factory=list)

    @property
    def to_move(self) -> int:
        return len(self.history) % 2

    def legal(self) -> list[int]:
        return [col for col in range(COLS) if self.heights[col] < ROWS]

    def play(self, col: int) -> None:
        if self.heights[col] >= ROWS:
            raise ValueError(f"column {col + 1} is full")
        self.stones[self.to_move] |= bit(col, self.heights[col])
        self.heights[col] += 1
        self.history.append(col)

    def undo(self) -> None:
        col = self.history.pop()
        self.heights[col] -= 1
        self.stones[self.to_move] &= ~bit(col, self.heights[col])

    def winner(self) -> int | None:
        for player in (0, 1):
            if has_four(self.stones[player]):
                return player
        return None

    @property
    def full(self) -> bool:
        return len(self.history) == ROWS * COLS

    def wins_with(self, col: int, player: int) -> bool:
        """Would `player` complete four by dropping in `col` now?"""
        if self.heights[col] >= ROWS:
            return False
        return has_four(self.stones[player] | bit(col, self.heights[col]))

    def copy(self) -> Board:
        return Board(list(self.stones), list(self.heights), list(self.history))

    def grid(self) -> list[str]:
        """Rows top to bottom, 'X' for the first player, 'O' for the second."""
        out = []
        for row in range(ROWS - 1, -1, -1):
            line = ""
            for col in range(COLS):
                cell = bit(col, row)
                line += "X" if self.stones[0] & cell else "O" if self.stones[1] & cell else "."
            out.append(line)
        return out


# --- search -------------------------------------------------------------------------------------------

_WEIGHTS = (0, 1, 8, 64)


def evaluate(board: Board, player: int) -> int:
    """Open lines of four: each scores by how many of its cells one side already holds."""
    mine, theirs = board.stones[player], board.stones[1 - player]
    score = 0
    for window in _windows():
        a = (mine & window).bit_count()
        b = (theirs & window).bit_count()
        if a and not b:
            score += _WEIGHTS[a]
        elif b and not a:
            score -= _WEIGHTS[b]
    return score


def negamax(board: Board, depth: int, alpha: int, beta: int) -> int:
    player = board.to_move
    moves = [col for col in CENTER_ORDER if board.heights[col] < ROWS]
    if not moves:
        return 0
    for col in moves:
        if board.wins_with(col, player):
            return WIN_SCORE + depth  # sooner wins score higher
    if depth == 0:
        return evaluate(board, player)
    best = -WIN_SCORE * 2
    for col in moves:
        board.play(col)
        value = -negamax(board, depth - 1, -beta, -alpha)
        board.undo()
        best = max(best, value)
        alpha = max(alpha, value)
        if alpha >= beta:
            break
    return best


def search_move(board: Board, depth: int, rng: Rng) -> int:
    """Best column at `depth` plies; equal scores go to a seeded coin."""
    player = board.to_move
    moves = [col for col in CENTER_ORDER if board.heights[col] < ROWS]
    wins = [col for col in moves if board.wins_with(col, player)]
    if wins:
        return rng.choice(sorted(wins))
    scored = []
    for col in moves:
        board.play(col)
        scored.append((-negamax(board, depth - 1, -WIN_SCORE * 2, WIN_SCORE * 2), col))
        board.undo()
    best = max(value for value, _ in scored)
    return rng.choice(sorted(col for value, col in scored if value == best))


def win_block_move(board: Board, rng: Rng) -> int:
    player = board.to_move
    legal = board.legal()
    wins = [col for col in legal if board.wins_with(col, player)]
    if wins:
        return rng.choice(wins)
    blocks = [col for col in legal if board.wins_with(col, 1 - player)]
    if blocks:
        return rng.choice(blocks)
    return rng.choice(legal)


def opponent_move(name: str, board: Board, rng: Rng) -> int:
    if name == "random":
        return rng.choice(board.legal())
    if name == "win-block":
        return win_block_move(board, rng)
    if name.startswith("negamax-"):
        return search_move(board, int(name.split("-")[1]), rng)
    raise ValueError(f"unknown opponent {name!r}")


# --- task ---------------------------------------------------------------------------------------------


def seed_setup(seed: int) -> tuple[str, bool]:
    """(opponent, the player moves first) for a seed."""
    return LADDER[(seed - 1) % len(LADDER)], ((seed - 1) // len(LADDER)) % 2 == 0


def move_facts(board: Board, col: int) -> list[str]:
    me = board.to_move
    facts = []
    if board.wins_with(col, me):
        return ["wins the game"]
    if board.wins_with(col, 1 - me):
        facts.append("takes the cell where the opponent could complete four")
    board.play(col)
    if any(board.wins_with(c, 1 - me) for c in board.legal()):
        facts.append("after it the opponent can complete four on their next move")
    board.undo()
    return facts or ["no four is completed or allowed on the next move"]


INSTRUCTIONS = (
    "Choose the column for your disc. It drops to the lowest empty row of that column. Each option names the "
    "column, the row where the disc lands and what follows immediately. Goal: win the game."
)


def render_state(board: Board, me: int, opponent_first: bool) -> str:
    you, them = ("X", "O") if me == 0 else ("O", "X")
    first = "the opponent" if opponent_first else "you"
    header = [
        f"Connect Four, 7 columns x 6 rows (column 1 on the left, row 1 at the bottom). You play {you}; the opponent "
        f"plays {them}; {first} moved first. Four in a row across, up or diagonally wins.",
        f"Move {len(board.history) + 1}. It is your turn.",
        "    " + " ".join(str(c + 1) for c in range(COLS)),
    ]
    rows = [f"{ROWS - i:>2}  " + " ".join(line) for i, line in enumerate(board.grid())]
    return "\n".join(header + rows)


@dataclass(frozen=True, slots=True)
class Connect4View:
    board: Board
    me: int


class Connect4Task:
    game = "connect4"
    track = "macro"
    default_key = ""

    def __init__(self) -> None:
        self.board = Board()
        self.opponent = LADDER[0]
        self.me = 0
        self.rng = Rng(0)
        self.missed_wins = 0
        self.allowed_wins = 0

    def reset(self, seed: int) -> None:
        self.opponent, first = seed_setup(seed)
        self.me = 0 if first else 1
        self.board = Board()
        self.rng = Rng.derive("connect4", "opponent", seed)
        self.missed_wins = 0
        self.allowed_wins = 0
        self._opponent_turns()

    def _opponent_turns(self) -> None:
        if not self.done and self.board.to_move != self.me:
            self.board.play(opponent_move(self.opponent, self.board, self.rng))

    @property
    def done(self) -> bool:
        return self.board.winner() is not None or self.board.full

    @property
    def steps(self) -> int:
        return len(self.board.history)

    def decision_point(self) -> DecisionPoint:
        board = self.board
        options = []
        for col in board.legal():
            facts = "; ".join(move_facts(board, col))
            where = f"column {col + 1}, the disc lands in row {board.heights[col] + 1}"
            options.append(Option(f"c{col + 1}", f"{where}: {facts}"))
        state = render_state(board, self.me, opponent_first=self.me == 1)
        return DecisionPoint(Question(state, INSTRUCTIONS, tuple(options)), Connect4View(board.copy(), self.me))

    def apply(self, key: str) -> None:
        col = int(key.removeprefix("c")) - 1
        legal = self.board.legal()
        if col not in legal:
            raise ValueError(f"illegal Connect Four move {key!r}")
        if not self.board.wins_with(col, self.me) and any(self.board.wins_with(c, self.me) for c in legal):
            self.missed_wins += 1
        if self._gives_win(col) and not all(self._gives_win(c) for c in legal):
            self.allowed_wins += 1
        self.board.play(col)
        self._opponent_turns()

    def held(self, key: str) -> str:
        return key

    def _gives_win(self, col: int) -> bool:
        """Does playing `col` leave the opponent an immediate win (and not win outright)?"""
        board = self.board
        if board.wins_with(col, self.me):
            return False
        board.play(col)
        gives = any(board.wins_with(c, 1 - self.me) for c in board.legal())
        board.undo()
        return gives

    def result(self) -> str:
        winner = self.board.winner()
        if winner is None:
            return "draw" if self.board.full else "unfinished"
        return "win" if winner == self.me else "loss"

    def score(self) -> float:
        return {"win": 1.0, "draw": 0.5}.get(self.result(), 0.0)

    def metrics(self) -> dict[str, Metric]:
        return {
            "result": self.result(),
            "opponent": self.opponent,
            "first": self.me == 0,
            "moves": len(self.board.history),
            "missed_wins": self.missed_wins,
            "allowed_wins": self.allowed_wins,
        }

    def snapshot(self) -> JSON:
        return {
            "grid": self.board.grid(),
            "you": "X" if self.me == 0 else "O",
            "opponent": self.opponent,
            "last": self.board.history[-1] + 1 if self.board.history else None,
            "result": self.result() if self.done else None,
        }

    def close(self) -> None:
        pass


def reference_move(view: Connect4View, depth: int, rng: Rng) -> str:
    return f"c{search_move(view.board.copy(), depth, rng) + 1}"
