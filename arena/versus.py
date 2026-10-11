"""Site data for Versus: models compared on the same seeds, and direct games between models.

`webui/data/versus.json` holds what the Versus pages need to pick a match without opening replays: per
(board, game) each model's score, length and end on every seed, each pair's lead changes and chases, the
reference player's score on the seed (par), and the matches most worth watching. The replays themselves are the
usual replay files (`replays/<board>/<game>/<player>/<seed>.json.gz`), exported for every model episode of these
games, plus `replays/duel/<pair>/<seed>-<game>.json.gz` for the direct games.

Two runs on the same seed are compared position by position: by decision on the turn-based boards (a Tetris
piece, a Snake step, a frame), by game step on the real-time board, where each model reacts with its own delay.
At every position a run counts with its latest score, and a finished run with its final score. The lead changes
when the side ahead differs from the side last ahead (a level score keeps the last leader). A chase is a run that
ends while the other is not ahead of it: the survivor plays on against a fixed target. The site recomputes the
same events from the replays (site/src/lib/versus.ts); both follow tests/golden/versus-series.json.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from arena import duel
from arena.core import JSON
from arena.logs import RESULTS, read_decisions, read_episodes, read_final, run_dir
from arena.suite import SUITES, Suite, load_suite

SCHEMA = 1
DUEL_SUITE = "duel-v0.1"

# (board, game) compared on the same seeds. Tetris on the frame and real-time boards is left out: every model
# clears no line there, so a match has nothing to compare but how many pieces each placed.
GAMES: tuple[tuple[str, str], ...] = (
    ("macro", "tetris"),
    ("macro", "snake"),
    ("macro", "pong"),
    ("macro", "breakout"),
    ("frame", "pong"),
    ("frame", "breakout"),
    ("realtime", "pong"),
    ("realtime", "breakout"),
)
EXCLUDED: dict[tuple[str, str], str] = {
    ("frame", "tetris"): "Every model clears 0 lines on the frame board; only survival would differ.",
    ("realtime", "tetris"): "Every model clears 0 lines on the real-time board; only survival would differ.",
    ("macro", "connect4"): "Connect Four is compared in direct games between the models.",
}
UNITS = {("macro", "tetris"): "piece", ("macro", "snake"): "step", ("macro", "pong"): "decision"}
PICKS_PER_GAME = 3


def score_of(game: str, snapshot: JSON) -> float:
    """The running score a snapshot shows, on the same scale as the episode score."""
    if game == "tetris":
        return float(snapshot["lines"])
    if game == "snake":
        return float(snapshot["eaten"])
    if game == "pong":
        return float(snapshot["score"][0] - snapshot["score"][1])
    if game == "breakout":
        return float(snapshot["score"])
    raise KeyError(f"no running score for {game!r}")


def sync_unit(board: str) -> str:
    return "step" if board == "realtime" else "decision"


@dataclass(frozen=True)
class Series:
    """A run as (position, score) points, ascending, starting at 0; `end` is where it stopped."""

    points: tuple[tuple[int, float], ...]
    end: int
    final: float

    def at(self, position: int) -> float:
        if position >= self.end:
            return self.final
        value = self.points[0][1]
        for at, score in self.points:
            if at > position:
                break
            value = score
        return value


def series(game: str, decisions: Sequence[JSON], final: JSON, unit: str) -> Series:
    """The score along a run: by decision index, or by the step each decision observed."""
    points: list[tuple[int, float]] = []
    for item in decisions:
        position = int(item["i"]) if unit == "decision" else int(item["step"])
        points.append((position, score_of(game, item["snapshot"])))
    end = len(decisions) if unit == "decision" else int(final["step"])
    final_score = score_of(game, final["snapshot"])
    if not points:
        points = [(0, final_score)]
    return Series(tuple(points), end, final_score)


@dataclass(frozen=True)
class Comparison:
    lead_changes: int
    chase: bool
    margin: float


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def compare(a: Series, b: Series) -> Comparison:
    """Lead changes and chase between two runs of the same seed (see the module docstring)."""
    positions = sorted({p for p, _ in a.points} | {p for p, _ in b.points} | {a.end, b.end})
    leader = 0
    changes = 0
    for position in positions:
        side = _sign(a.at(position) - b.at(position))
        if side and leader and side != leader:
            changes += 1
        if side:
            leader = side
    chase = (a.end < b.end and b.at(a.end) <= a.final) or (b.end < a.end and a.at(b.end) <= b.final)
    return Comparison(changes, chase, a.final - b.final)


def _end_cause(game: str, metrics: JSON) -> str:
    if game == "tetris":
        return "topped out" if metrics.get("topped_out") else "piece cap"
    if game == "snake":
        if metrics.get("died"):
            return "hit its own body" if metrics.get("death") == "body" else "hit the wall"
        return "starved" if metrics.get("starved") else "step cap"
    if game == "pong":
        return "lost the game" if metrics.get("game_over") else "step cap"
    if game == "breakout":
        if metrics.get("game_over"):
            return "lost every life"
        return "stopped serving" if metrics.get("idle_end") else "step cap"
    return ""


def _runs(suite: Suite, seed_set: str, board: str, game: str, player: str, *, results: Path) -> dict[int, Series]:
    directory = run_dir(suite.id, seed_set, board, game, player, results=results)
    unit = sync_unit(board)
    found: dict[int, Series] = {}
    for episode in read_episodes(directory):
        seed = int(episode["seed"])
        path = directory / "decisions" / f"{seed}.jsonl.gz"
        final = read_final(path)
        if final is None:
            continue
        found[seed] = series(game, list(read_decisions(path)), final, unit)
    return found


def _picks(
    matches: dict[str, dict[str, dict[str, list[float]]]],
    episodes: dict[str, dict[str, dict[str, list[object]]]],
    floors: dict[str, float],
    per_game: int,
) -> list[JSON]:
    """The matches most worth watching, `per_game` per game: most lead changes, then a chase, then the closest
    finish. A match where both runs end on the game's floor (every Pong point lost, no Tetris line) is left out:
    its lead changes are only the order in which both runs lost."""
    picks: list[JSON] = []
    for key, by_pair in matches.items():
        board, game = key.split("/")
        floor = floors.get(key)
        rows = []
        for pair, by_seed in by_pair.items():
            a, b = duel.split_pair(pair)
            for seed, row in by_seed.items():
                finals = (episodes[key][a][seed][0], episodes[key][b][seed][0])
                if floor is not None and all(f == floor for f in finals):
                    continue
                rows.append((int(row[0]), int(row[1]), abs(row[2]), pair, int(seed)))
        rows.sort(key=lambda r: (-r[0], -r[1], r[2], r[3], r[4]))
        for changes, chase, margin, pair, number in rows[:per_game]:
            a, b = duel.split_pair(pair)
            picks.append(
                {
                    "board": board,
                    "game": game,
                    "a": a,
                    "b": b,
                    "seed": number,
                    "lead_changes": changes,
                    "chase": bool(chase),
                    "margin": margin,
                }
            )
    return picks


def _duel_section(seed_set: str, results: Path, suites: Path) -> JSON | None:
    try:
        suite = load_suite(DUEL_SUITE, suites)
    except FileNotFoundError:
        return None
    base = results / suite.id / seed_set / duel.BOARD / duel.GAME
    if not base.exists():
        return None
    games: dict[str, list[JSON]] = {}
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        rows = duel.read_games(directory)
        if rows:
            games[directory.name] = [
                {
                    "seed": int(g["seed"]),
                    "game_no": int(g["game_no"]),
                    "x": g["x"],
                    "o": g["o"],
                    "result": g["result"],
                    "moves": int(g["moves"]),
                    "missed_wins": g["missed_wins"],
                    "allowed_wins": g["allowed_wins"],
                    "latency_ms": g["latency_ms"],
                }
                for g in rows
            ]
    if not games:
        return None
    report = duel.score(suite, seed_set, results=results)
    seeds = suite.game(duel.BOARD, duel.GAME).seeds[seed_set]
    return {
        "suite": suite.id,
        "seed_set": seed_set,
        "openings": {str(seed): [c + 1 for c in duel.opening(seed)] for seed in seeds},
        "games": games,
        "ratings": report["ratings"],
        "pairs": report["pairs"],
    }


def write_duel_replays(seed_set: str, out: Path, results: Path, suites: Path = SUITES) -> int:
    """One replay file per direct game: both sides' decisions, the final position and the result."""
    try:
        suite = load_suite(DUEL_SUITE, suites)
    except FileNotFoundError:
        return 0
    base = results / suite.id / seed_set / duel.BOARD / duel.GAME
    if not base.exists():
        return 0
    count = 0
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        for g in duel.read_games(directory):
            seed, game_no = int(g["seed"]), int(g["game_no"])
            source = duel.decisions_file(directory, seed, game_no)
            data = {
                "schema": SCHEMA,
                "pair": g["pair"],
                "seed": seed,
                "game_no": game_no,
                "x": g["x"],
                "o": g["o"],
                "opening": g["opening"],
                "result": g["result"],
                "decisions": list(read_decisions(source)),
                "final": read_final(source),
            }
            target = out / "replays" / "duel" / str(g["pair"]) / f"{seed}-{game_no}.json.gz"
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
            target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
            count += 1
    return count


def versus_data(
    suite: Suite,
    seed_set: str,
    models: Iterable[str],
    *,
    results: Path = RESULTS,
    suites: Path = SUITES,
) -> JSON:
    model_list = list(models)
    games_out: list[JSON] = []
    episodes: dict[str, dict[str, dict[str, list[object]]]] = {}
    matches: dict[str, dict[str, dict[str, list[float]]]] = {}
    par: dict[str, dict[str, float]] = {}
    delays: dict[str, dict[str, int]] = {}
    floors: dict[str, float] = {}
    for board, game in GAMES:
        if board not in suite.boards or game not in suite.board(board).games:
            continue
        key = f"{board}/{game}"
        spec = suite.game(board, game)
        games_out.append(
            {
                "board": board,
                "game": game,
                "sync": sync_unit(board),
                "unit": UNITS.get((board, game), "step" if board == "realtime" else "frame"),
                "seeds": spec.seeds[seed_set],
            }
        )
        runs: dict[str, dict[int, Series]] = {}
        episodes[key] = {}
        for model in model_list:
            directory = run_dir(suite.id, seed_set, board, game, model, results=results)
            lines = read_episodes(directory)
            if not lines:
                continue
            runs[model] = _runs(suite, seed_set, board, game, model, results=results)
            episodes[key][model] = {
                str(e["seed"]): [
                    e["score"],
                    runs[model][int(e["seed"])].end if int(e["seed"]) in runs[model] else None,
                    _end_cause(game, e.get("metrics", {})),
                ]
                for e in lines
            }
            if board == "realtime":
                delays.setdefault(key, {})[model] = int(lines[0].get("delay_steps", 0))
        finals = [run.final for by_seed in runs.values() for run in by_seed.values()]
        if finals:
            floors[key] = min(finals)
        anchor_board = suite.board(board).based_on or board
        reference = read_episodes(run_dir(suite.id, seed_set, anchor_board, game, "reference", results=results))
        par[key] = {str(e["seed"]): e["score"] for e in reference}
        matches[key] = {}
        for a, b in combinations(sorted(runs), 2):
            pair_rows: dict[str, list[float]] = {}
            for seed in sorted(set(runs[a]) & set(runs[b])):
                c = compare(runs[a][seed], runs[b][seed])
                pair_rows[str(seed)] = [c.lead_changes, int(c.chase), c.margin]
            matches[key][duel.pair_id(a, b)] = pair_rows
    return {
        "schema": SCHEMA,
        "suite": suite.id,
        "seed_set": seed_set,
        "models": model_list,
        "games": games_out,
        "excluded": [{"board": b, "game": g, "reason": reason} for (b, g), reason in EXCLUDED.items()],
        "episodes": episodes,
        "matches": matches,
        "par": par,
        "delays": delays,
        "floors": floors,
        "picks": _picks(matches, episodes, floors, PICKS_PER_GAME),
        "duel": _duel_section(seed_set, results, suites),
    }
