"""Direct games: two models play Connect Four against each other (suites of kind "duel").

Each pair of models plays every opening twice, once with each model as X. An opening is the first two moves,
fixed by the seed, so a pair's games start from positions neither model chose; mirror images count as one
opening. After the opening both sides are asked exactly what a macro-board player sees (`arena.games.connect4`:
the same state text, instructions and option facts, from the side to move), through the same decision protocol,
one model per side. A game is won by four in a row and drawn when the board fills.

    results/<suite>/<seed set>/direct/connect4/<a>~<b>/episodes.jsonl              one line per finished game
    results/<suite>/<seed set>/direct/connect4/<a>~<b>/decisions/<seed>-<g>.jsonl.gz   both sides' decisions

`<a>~<b>` is the pair in sorted order; game 1 of an opening has `a` as X, game 2 has `b` as X.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

from arena import __version__, logs
from arena.client import DEFAULT_SERVER, ModelClient
from arena.core import JSON, Decision, DecisionPoint, Option, Player, Question
from arena.episode import DecisionRecord
from arena.games.connect4 import COLS, INSTRUCTIONS, Board, move_facts, render_state
from arena.gpu import gpu_processes
from arena.logs import RESULTS, DecisionWriter, append_jsonl, read_final, read_jsonl
from arena.players import TextPlayer
from arena.registry import contestants
from arena.seeding import Rng
from arena.suite import Suite, lock_differences, locked_digest

BOARD = "direct"
GAME = "connect4"
SIDES = ("X", "O")


# --- openings ---------------------------------------------------------------------------------------------


def _canonical_openings() -> list[tuple[int, int]]:
    """The 25 two-move openings up to mirror image: X's column left of centre, or in the centre with O's not
    right of it (0-based columns)."""
    centre = COLS // 2
    return [(x, o) for x in range(centre + 1) for o in range(COLS) if x < centre or o <= centre]


OPENINGS: tuple[tuple[int, int], ...] = tuple(Rng.derive("connect4-duel", "openings").shuffled(_canonical_openings()))


def opening(seed: int) -> tuple[int, int]:
    """X's and O's first columns (0-based) for a seed. Seeds 1-25 give the 25 openings once each."""
    return OPENINGS[(seed - 1) % len(OPENINGS)]


def pair_id(a: str, b: str) -> str:
    first, second = sorted((a, b))
    if first == second:
        raise ValueError(f"a pair needs two different players, got {a!r} twice")
    return f"{first}~{second}"


def split_pair(pair: str) -> tuple[str, str]:
    a, b = pair.split("~")
    return a, b


def x_player(pair: str, game_no: int) -> str:
    """Who plays X in game `game_no` (1 or 2) of an opening."""
    a, b = split_pair(pair)
    return a if game_no == 1 else b


# --- the game ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DuelView:
    board: Board
    me: int


class Connect4Duel:
    """Connect Four where both sides are players. Deterministic given the seed and the moves played."""

    game = GAME

    def __init__(self) -> None:
        self.board = Board()
        self.opening: tuple[int, int] = (0, 0)
        self.missed_wins = [0, 0]
        self.allowed_wins = [0, 0]

    def reset(self, seed: int) -> None:
        self.board = Board()
        self.opening = opening(seed)
        for col in self.opening:
            self.board.play(col)
        self.missed_wins = [0, 0]
        self.allowed_wins = [0, 0]

    @property
    def done(self) -> bool:
        return self.board.winner() is not None or self.board.full

    @property
    def side(self) -> int:
        """0 when X is to move, 1 when O is."""
        return self.board.to_move

    @property
    def steps(self) -> int:
        return len(self.board.history)

    def decision_point(self) -> DecisionPoint:
        board, me = self.board, self.board.to_move
        options = []
        for col in board.legal():
            facts = "; ".join(move_facts(board, col))
            where = f"column {col + 1}, the disc lands in row {board.heights[col] + 1}"
            options.append(Option(f"c{col + 1}", f"{where}: {facts}"))
        state = render_state(board, me, opponent_first=me == 1)
        return DecisionPoint(Question(state, INSTRUCTIONS, tuple(options)), DuelView(board.copy(), me))

    def apply(self, key: str) -> None:
        board, me = self.board, self.board.to_move
        col = int(key.removeprefix("c")) - 1
        legal = board.legal()
        if col not in legal:
            raise ValueError(f"illegal Connect Four move {key!r}")
        if not board.wins_with(col, me) and any(board.wins_with(c, me) for c in legal):
            self.missed_wins[me] += 1
        if self._gives_win(col) and not all(self._gives_win(c) for c in legal):
            self.allowed_wins[me] += 1
        board.play(col)

    def _gives_win(self, col: int) -> bool:
        board, me = self.board, self.board.to_move
        if board.wins_with(col, me):
            return False
        board.play(col)
        gives = any(board.wins_with(c, 1 - me) for c in board.legal())
        board.undo()
        return gives

    def result(self) -> str:
        """'X', 'O', 'draw' or 'unfinished'."""
        winner = self.board.winner()
        if winner is None:
            return "draw" if self.board.full else "unfinished"
        return SIDES[winner]

    def snapshot(self) -> JSON:
        board = self.board
        return {
            "grid": board.grid(),
            "to_move": SIDES[board.to_move],
            "last": board.history[-1] + 1 if board.history else None,
            "moves": len(board.history),
            "result": self.result() if self.done else None,
        }


# --- one game ---------------------------------------------------------------------------------------------


def duel_rng(suite_id: str, seed: int, game_no: int, index: int) -> Rng:
    """Option order and tie-breaks of one decision; it depends on the game, not on who plays it."""
    return Rng.derive(suite_id, BOARD, GAME, seed, game_no, index, "decide")


@dataclass(frozen=True, slots=True)
class DuelOutcome:
    result: str
    moves: int
    decisions: tuple[int, int]
    forced: tuple[int, int]
    calls: tuple[int, int]


def play_duel(
    task: Connect4Duel,
    players: tuple[Player, Player],
    seed: int,
    game_no: int,
    *,
    suite_id: str,
    on_decision: Callable[[int, DecisionRecord], None] | None = None,
) -> DuelOutcome:
    """Play one game; `players` is (X, O). A question with a single legal option is not asked."""
    task.reset(seed)
    for player in players:
        player.start(seed)
    decisions, forced, calls = [0, 0], [0, 0], [0, 0]
    index = 0
    while not task.done:
        side = task.side
        point = task.decision_point()
        snapshot, step = task.snapshot(), task.steps
        options = point.question.options
        if len(options) == 1:
            decision = Decision(options[0].key, (), forced=True)
            forced[side] += 1
        else:
            decision = players[side].decide(point, duel_rng(suite_id, seed, game_no, index))
            if decision.choice not in point.question.keys:
                raise ValueError(f"{players[side].id} chose {decision.choice!r}, not an option of decision {index}")
            calls[side] += len(decision.calls)
        decisions[side] += 1
        if on_decision is not None:
            on_decision(side, DecisionRecord(index, step, snapshot, point.question, decision))
        task.apply(decision.choice)
        index += 1
    return DuelOutcome(
        task.result(), task.steps, (decisions[0], decisions[1]), (forced[0], forced[1]), (calls[0], calls[1])
    )


# --- runs ---------------------------------------------------------------------------------------------------


def pair_dir(suite_id: str, seed_set: str, pair: str, *, results: Path = RESULTS) -> Path:
    return results / suite_id / seed_set / BOARD / GAME / pair


def decisions_file(directory: Path, seed: int, game_no: int) -> Path:
    return directory / "decisions" / f"{seed}-{game_no}.jsonl.gz"


def read_games(directory: Path) -> list[JSON]:
    """Game lines of a pair, the last one per (seed, game) winning, in seed then game order."""
    by_key: dict[tuple[int, int], JSON] = {}
    for item in read_jsonl(directory / "episodes.jsonl"):
        by_key[(int(item["seed"]), int(item["game_no"]))] = item
    return [by_key[key] for key in sorted(by_key)]


def _latency(values: list[float]) -> JSON | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)], 3),
        "n": len(ordered),
    }


def _model_info(player_id: str) -> JSON:
    c = contestants()[player_id]
    return {
        "family": c.family,
        "repository": c.repository,
        "revision": c.revision,
        "base_model": c.base_model,
        "preset": c.preset,
        "config_sha": c.config_sha,
    }


def play_game(
    suite: Suite,
    seed_set: str,
    pair: str,
    seed: int,
    game_no: int,
    *,
    players: dict[str, Player],
    results: Path = RESULTS,
    lock: str | None = None,
) -> tuple[JSON | None, JSON | None]:
    """Play and log one game. Returns (game line, None) or (None, error line)."""
    x_id = x_player(pair, game_no)
    o_id = next(p for p in split_pair(pair) if p != x_id)
    directory = pair_dir(suite.id, seed_set, pair, results=results)
    writer = DecisionWriter(decisions_file(directory, seed, game_no))
    ids = (x_id, o_id)
    latencies: dict[str, list[float]] = {x_id: [], o_id: []}

    def record(side: int, item: DecisionRecord) -> None:
        latencies[ids[side]].extend(call.latency_ms for call in item.decision.calls)
        writer.write(item, extra={"side": SIDES[side], "player": ids[side]})

    task = Connect4Duel()
    base: JSON = {
        "suite": suite.id,
        "lock": lock,
        "seed_set": seed_set,
        "board": BOARD,
        "game": GAME,
        "pair": pair,
        "seed": seed,
        "game_no": game_no,
        "x": x_id,
        "o": o_id,
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    clock = time.perf_counter()
    try:
        outcome = play_duel(task, (players[x_id], players[o_id]), seed, game_no, suite_id=suite.id, on_decision=record)
        writer.finish(task.snapshot(), task.steps)
        writer.commit()
    except Exception as error:  # a failed game must not stop the others; it runs again next time
        writer.discard()
        return None, {**base, "error": f"{type(error).__name__}: {error}"}
    winner = {"X": x_id, "O": o_id}.get(outcome.result)
    game: JSON = {
        **base,
        "opening": [c + 1 for c in opening(seed)],
        "result": outcome.result,
        "winner": winner,
        "points": {x_id: _points(outcome.result, "X"), o_id: _points(outcome.result, "O")},
        "moves": outcome.moves,
        "decisions": {x_id: outcome.decisions[0], o_id: outcome.decisions[1]},
        "forced": {x_id: outcome.forced[0], o_id: outcome.forced[1]},
        "calls": {x_id: outcome.calls[0], o_id: outcome.calls[1]},
        "missed_wins": {x_id: task.missed_wins[0], o_id: task.missed_wins[1]},
        "allowed_wins": {x_id: task.allowed_wins[0], o_id: task.allowed_wins[1]},
        "latency_ms": {pid: _latency(values) for pid, values in latencies.items()},
        "model": {pid: _model_info(pid) for pid in ids if pid in contestants()},
        "arena": __version__,
        "seconds": round(time.perf_counter() - clock, 3),
    }
    return game, None


def _points(result: str, side: str) -> float:
    if result == "draw":
        return 0.5
    return 1.0 if result == side else 0.0


def schedule(models: Sequence[str]) -> list[str]:
    """Every pair once, ordered so that consecutive pairs share a model where possible (fewer model loads)."""
    order: list[str] = []
    for i, first in enumerate(models):
        order.extend(pair_id(first, second) for second in models[i + 1 :])
    return order


def wait_for_room(
    pair: str, *, timeout: float = 900.0, poll: float = 5.0, say: Callable[[str], None] = logs.say
) -> None:
    """Wait until no model outside `pair` holds GPU memory: two models are loaded together during a game, and a
    third one still loaded from the previous pair could exhaust the GB10's unified memory. model-compose unloads
    an idle model after two minutes."""
    allowed = set(split_pair(pair))
    deadline = time.monotonic() + timeout
    announced = False
    while True:
        others = sorted({p.runtime for p in gpu_processes() if p.runtime and p.busy and p.runtime not in allowed})
        if not others:
            return
        if time.monotonic() > deadline:
            raise TimeoutError(f"models {others} stayed loaded for {timeout:.0f}s; stop them before {pair}")
        if not announced:
            say(f"waiting for {', '.join(others)} to unload before {pair}")
            announced = True
        time.sleep(poll)


@dataclass
class DuelSummary:
    finished: list[JSON]
    failed: list[JSON]
    skipped: int


def run_duels(
    suite: Suite,
    seed_set: str,
    pairs: Sequence[str],
    *,
    seeds: Sequence[int] | None = None,
    server: str = DEFAULT_SERVER,
    results: Path = RESULTS,
    make_player: Callable[[str], Player] | None = None,
    room: Callable[[str], None] | None = wait_for_room,
    progress: Callable[[str], None] | None = None,
) -> DuelSummary:
    """Play every missing game of `pairs` (resumable): each seed's two games, pair by pair."""
    say = progress or logs.say
    if suite.kind != "duel":
        raise ValueError(f"suite {suite.id} is not a duel suite")
    if seed_set == "test":
        problems = lock_differences(suite)
        if problems:
            raise RuntimeError("test seeds need a frozen suite matching this tree:\n  " + "\n  ".join(problems))
    elif seed_set != "dev":
        raise ValueError(f"seed set must be 'dev' or 'test', got {seed_set!r}")
    seed_list = list(seeds) if seeds is not None else suite.game(BOARD, GAME).seeds[seed_set]
    lock = locked_digest(suite) if seed_set == "test" else None
    known = contestants()

    def build(player_id: str) -> Player:
        if player_id not in known:
            raise KeyError(f"unknown model {player_id!r}; models {sorted(known)}")
        return TextPlayer(known[player_id], ModelClient(server), suite.group_size)

    factory = make_player or build
    summary = DuelSummary([], [], 0)
    for pair in pairs:
        directory = pair_dir(suite.id, seed_set, pair, results=results)
        done = {(int(g["seed"]), int(g["game_no"])) for g in read_games(directory)}
        todo = [(seed, game_no) for seed in seed_list for game_no in (1, 2) if (seed, game_no) not in done]
        summary.skipped += 2 * len(seed_list) - len(todo)
        if not todo:
            continue
        if room is not None:
            room(pair)
        players = {pid: factory(pid) for pid in split_pair(pair)}
        try:
            for seed, game_no in todo:
                game, error = play_game(
                    suite, seed_set, pair, seed, game_no, players=players, results=results, lock=lock
                )
                if game is not None:
                    append_jsonl(directory / "episodes.jsonl", game)
                    summary.finished.append(game)
                    say(
                        f"{pair} seed {seed} game {game_no}: {game['result']} in {game['moves']} moves "
                        f"({game['seconds']:.1f}s)"
                    )
                if error is not None:
                    append_jsonl(directory / "errors.jsonl", error)
                    summary.failed.append(error)
                    say(f"{pair} seed {seed} game {game_no}: FAILED {error['error']}")
        finally:
            for player in players.values():
                player.close()
    return summary


def all_pairs(models: Sequence[str]) -> list[str]:
    return [pair_id(a, b) for a, b in combinations(models, 2)]


# --- verification -------------------------------------------------------------------------------------------


class DuelMismatchError(AssertionError):
    pass


def verify_game(suite: Suite, seed_set: str, game: JSON, results: Path = RESULTS) -> int:
    """Replay one game from its log and demand the same questions, positions and result."""
    pair, seed, game_no = str(game["pair"]), int(game["seed"]), int(game["game_no"])
    path = decisions_file(pair_dir(suite.id, seed_set, pair, results=results), seed, game_no)
    log = list(logs.read_decisions(path))
    task = Connect4Duel()
    task.reset(seed)
    ids = (str(game["x"]), str(game["o"]))
    for i, entry in enumerate(log):
        if task.done:
            raise DuelMismatchError(f"the game ended before decision {i}; the log has {len(log)}")
        point = task.decision_point()
        q = point.question
        produced: JSON = {
            "i": i,
            "step": task.steps,
            "snapshot": task.snapshot(),
            "state": q.state,
            "instructions": q.instructions,
            "options": [{"key": o.key, "text": o.text} for o in q.options],
            "forced": len(q.options) == 1,
            "side": SIDES[task.side],
            "player": ids[task.side],
        }
        for name, value in produced.items():
            if entry[name] != value:
                raise DuelMismatchError(
                    f"decision {i}: {name} differs\n  logged: {entry[name]!r:.300}\n  now: {value!r:.300}"
                )
        task.apply(str(entry["choice"]))
    if not task.done:
        raise DuelMismatchError(f"the log ends after {len(log)} decisions but the game goes on")
    final = read_final(path)
    if final is None or final["snapshot"] != task.snapshot() or final["step"] != task.steps:
        raise DuelMismatchError("the final position differs from the logged one")
    if task.result() != game["result"]:
        raise DuelMismatchError(f"result {task.result()} differs from the logged {game['result']}")
    return len(log)


@dataclass(frozen=True)
class DuelVerified:
    pair: str
    seed: int
    game_no: int
    decisions: int
    problem: str | None


def verify(suite: Suite, seed_set: str, *, results: Path = RESULTS) -> Iterator[DuelVerified]:
    base = results / suite.id / seed_set / BOARD / GAME
    if not base.exists():
        return
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        for game in read_games(directory):
            key = (str(game["pair"]), int(game["seed"]), int(game["game_no"]))
            try:
                yield DuelVerified(*key, verify_game(suite, seed_set, game, results), None)
            except (DuelMismatchError, FileNotFoundError, KeyError) as error:
                yield DuelVerified(*key, 0, str(error))


# --- scores -------------------------------------------------------------------------------------------------


def _bradley_terry(players: list[str], games: list[JSON], iterations: int = 500) -> dict[str, float]:
    """Strengths by the MM algorithm (Hunter 2004), a draw counting as half a win for each side; a light prior
    (one drawn game against a virtual player of strength 1) keeps every strength finite."""
    wins = dict.fromkeys(players, 0.5)
    meetings: dict[str, dict[str, float]] = {p: {} for p in players}
    for g in games:
        x, o = str(g["x"]), str(g["o"])
        wins[x] += float(g["points"][x])
        wins[o] += float(g["points"][o])
        meetings[x][o] = meetings[x].get(o, 0.0) + 1
        meetings[o][x] = meetings[o].get(x, 0.0) + 1
    strength = dict.fromkeys(players, 1.0)
    for _ in range(iterations):
        updated = {}
        for p in players:
            denominator = 1.0 / (strength[p] + 1.0)
            denominator += sum(n / (strength[p] + strength[q]) for q, n in meetings[p].items())
            updated[p] = wins[p] / denominator
        mean = math.exp(statistics.fmean(math.log(v) for v in updated.values()))
        strength = {p: v / mean for p, v in updated.items()}
    return strength


def elo(strength: float) -> float:
    """Bradley-Terry strength on the Elo scale, the geometric mean of all players at 1500."""
    return 1500.0 + 400.0 * math.log10(strength)


def score(suite: Suite, seed_set: str, *, results: Path = RESULTS, replicates: int | None = None) -> JSON:
    """Pair records, game pairs per opening, and Bradley-Terry ratings with intervals from resampling openings."""
    base = results / suite.id / seed_set / BOARD / GAME
    games = [g for d in sorted(base.iterdir()) if d.is_dir() for g in read_games(d)] if base.exists() else []
    players = sorted({str(g[k]) for g in games for k in ("x", "o")})
    pairs: dict[str, JSON] = {}
    for g in games:
        entry = pairs.setdefault(str(g["pair"]), {"games": 0, "points": {}, "wins": {}, "draws": 0, "openings": {}})
        entry["games"] += 1
        for pid in (g["x"], g["o"]):
            entry["points"][pid] = entry["points"].get(pid, 0.0) + float(g["points"][pid])
            entry["wins"].setdefault(pid, 0)
        if g["winner"] is None:
            entry["draws"] += 1
        else:
            entry["wins"][g["winner"]] += 1
        opening_points = entry["openings"].setdefault(str(g["seed"]), {})
        for pid in (g["x"], g["o"]):
            opening_points[pid] = opening_points.get(pid, 0.0) + float(g["points"][pid])
    ratings: JSON = {}
    if players:
        point = _bradley_terry(players, games)
        seeds = sorted({int(g["seed"]) for g in games})
        rounds = replicates if replicates is not None else min(suite.bootstrap, 400)
        rng = Rng.derive(suite.id, seed_set, "duel-bootstrap")
        samples: dict[str, list[float]] = {p: [] for p in players}
        by_seed: dict[int, list[JSON]] = {}
        for g in games:
            by_seed.setdefault(int(g["seed"]), []).append(g)
        for _ in range(rounds):
            drawn = [g for _ in seeds for g in by_seed[seeds[rng.below(len(seeds))]]]
            strength = _bradley_terry(players, drawn, iterations=200)
            for p in players:
                samples[p].append(elo(strength[p]))
        alpha = (1.0 - suite.confidence) / 2
        for p in players:
            ordered = sorted(samples[p])
            low = ordered[int(alpha * (len(ordered) - 1))] if ordered else None
            high = ordered[int((1 - alpha) * (len(ordered) - 1))] if ordered else None
            played = [g for g in games if p in (g["x"], g["o"])]
            ratings[p] = {
                "elo": round(elo(point[p]), 1),
                "interval": [round(low, 1), round(high, 1)] if low is not None and high is not None else None,
                "games": len(played),
                "points": sum(float(g["points"][p]) for g in played),
                "missed_wins": sum(int(g["missed_wins"][p]) for g in played),
                "allowed_wins": sum(int(g["allowed_wins"][p]) for g in played),
            }
    return {
        "suite": suite.id,
        "seed_set": seed_set,
        "lock": locked_digest(suite),
        "games": len(games),
        "ratings": ratings,
        "pairs": pairs,
    }
