"""The README's tables, recomputed from the files under results/.

    uv run python scripts/stats.py                  every table
    uv run python scripts/stats.py --tables 5,8     some of them
    uv run python scripts/stats.py --pairs          adjacent pairs of each board, for the text

Tables 1, 3, 5, 6, 7 and 9 read the scores, latency and bias of suite v0.1, its episode lines, and the direct
games of duel-v0.1. Table 8 reads every decision of the Snake macro games and of the direct games: from the decision
logs a run leaves under results/ (git ignores them), otherwise from the replays the site ships in
webui/data/replays, which carry the same decisions for every model game. Its random row needs random's own logs:
`uv run arena run --board macro --game snake --player random --seeds test` writes them in seconds. Tables 2, 4 and
10 are prose. Charts: scripts/charts.py.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any

from arena.registry import contestants

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "webui" / "data" / "replays"
SUITE, DUEL = "v0.1", "duel-v0.1"
BOARDS = ("macro", "frame", "realtime")
ANCHORS = ("random", "reference")
#: The raw score of each game, as the README names it.
SCORE_NAMES = {
    "tetris": "Tetris lines",
    "snake": "Snake food",
    "connect4": "Connect Four score",
    "pong": "Pong points",
    "breakout": "Breakout points",
}
#: What Snake and Connect Four options say about a move (arena/games/snake.py, arena/games/connect4.py).
ENDS_GAME = "so the game ends"
WINS = "wins the game"
GIVES_FOUR = "after it the opponent can complete four"


@dataclass(frozen=True)
class Results:
    root: Path

    def suite(self) -> Path:
        return self.root / SUITE

    def duel(self) -> Path:
        return self.root / DUEL


def load(path: Path) -> Any:
    return json.loads(path.read_text())


@cache
def players() -> dict[str, str]:
    """Model id to title, in the order of model-compose.yml."""
    return {pid: c.title for pid, c in contestants().items()}


def title(pid: str) -> str:
    return players().get(pid, pid)


def models() -> list[str]:
    return list(players())


def scores(results: Results) -> dict[str, Any]:
    return dict(load(results.suite() / "scores-test.json"))


def duel_scores(results: Results) -> dict[str, Any]:
    return dict(load(results.duel() / "scores-test.json"))


def ranked(board: dict[str, Any]) -> list[str]:
    return [p for p in board["ranking"] if p not in ANCHORS]


def episodes(results: Results, board: str | None = None) -> Iterator[dict[str, Any]]:
    pattern = f"test/{board or '*'}/*/*/episodes.jsonl"
    for path in sorted(results.suite().glob(pattern)):
        for line in path.read_text().splitlines():
            yield json.loads(line)


def unzip(path: Path) -> str:
    with gzip.open(path, "rt") as f:
        return f.read()


def decisions(run: Path, replays: Path) -> list[list[dict[str, Any]]] | None:
    """Every decision of each episode in a results directory, one list per episode, from its decision logs or else
    from the site's replays of the same episodes; None unless one or the other has every episode."""
    expected = len((run / "episodes.jsonl").read_text().splitlines())
    logs = sorted((run / "decisions").glob("*.jsonl.gz"))
    if len(logs) == expected:
        return [[json.loads(line) for line in unzip(path).splitlines()] for path in logs]
    shipped = sorted(replays.glob("*.json.gz"))
    if len(shipped) == expected:
        return [json.loads(unzip(path))["decisions"] for path in shipped]
    return None


def num(x: float, digits: int = 1) -> str:
    """A number as the site prints it (site/src/lib/format.ts): halves away from zero, a true minus sign and no
    negative zero, so the README and the site agree to the last digit."""
    fixed = Decimal(abs(x)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"−{fixed}" if x < 0 and fixed else str(fixed)


def interval(ci: list[float], digits: int = 1) -> str:
    return f"[{num(ci[0], digits)}, {num(ci[1], digits)}]"


def share(percent: float) -> str:
    """A whole percentage, or one decimal where that would round a rare event down to 0."""
    return num(percent, 1 if 0 < percent < 0.5 else 0)


def pct(part: int, whole: int) -> str:
    return f"{part:,} of {whole:,} ({share(100 * part / whole)}%)" if whole else "none on offer"


def table(head: list[str], rows: list[list[str]], align: str = "") -> str:
    """A Markdown table; `align` has one character per column, l or r (left by default)."""
    rule = ["---:" if a == "r" else "---" for a in align.ljust(len(head), "l")]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(rule) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# --- latency and delay -------------------------------------------------------------------------------------------


def latency(results: Results, pid: str, board: str) -> list[float]:
    """Median ms per request of each probe game of a board (arena latency)."""
    games = load(results.suite() / "latency" / f"{pid}.json")["games"]
    return sorted(v["median_ms"] for k, v in games.items() if k.startswith(board + "/"))


def delays(results: Results) -> dict[str, list[int]]:
    """The reaction delay, in steps of 66.7 ms, that each model's real-time episodes ran with."""
    found: dict[str, set[int]] = {}
    for e in episodes(results, "realtime"):
        found.setdefault(e["player"], set()).add(int(e["delay_steps"]))
    return {p: sorted(ks) for p, ks in found.items()}


def span(values: list[int]) -> str:
    lo, hi = min(values), max(values)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def spread(ms: list[float]) -> str:
    """The median of a board's per-game medians, with their range when the games differ."""
    middle, lo, hi = (num(x, 0) for x in (statistics.median(ms), min(ms), max(ms)))
    return f"{middle} ms" if lo == hi else f"{middle} ms ({lo}–{hi})"


# --- tables --------------------------------------------------------------------------------------------------------


def table1(results: Results) -> str:
    s, d = scores(results)["boards"], duel_scores(results)["ratings"]
    k = delays(results)
    rows = [
        [
            title(pid),
            *(num(s[b]["players"][pid]["index"]) for b in BOARDS),
            num(d[pid]["elo"], 0),
            f"{num(statistics.median(latency(results, pid, 'frame')), 0)} ms",
            span(k[pid]),
        ]
        for pid in ranked(s["macro"])
    ]
    head = [
        "Model",
        "Macro index",
        "Frame index",
        "Real-time index",
        "Elo, Connect Four between models",
        "Per request, frame board",
        "Real-time delay (steps)",
    ]
    return "Table 1: Summary by model (index: random 0, reference 100)\n\n" + table(head, rows, "lrrrrrr")


def table3(results: Results) -> str:
    totals: dict[str, dict[str, float]] = {}
    for e in episodes(results):
        t = totals.setdefault(e["player"], {"calls": 0, "seconds": 0.0})
        t["calls"] += e["calls"]
        t["seconds"] += e["seconds"]
    k = delays(results)
    rows = []
    for pid in sorted(models(), key=lambda p: statistics.median(latency(results, p, "frame"))):
        frame, macro = latency(results, pid, "frame"), latency(results, pid, "macro")
        t = totals[pid]
        rows.append(
            [
                title(pid),
                spread(frame),
                spread(macro),
                span(k[pid]),
                f"{int(t['calls']):,}",
                f"{num(t['seconds'] / 3600)} h",
            ]
        )
    played = [t for p, t in totals.items() if p not in ANCHORS]
    rows.append(
        [
            "All ten",
            "",
            "",
            "",
            f"{int(sum(t['calls'] for t in played)):,}",
            f"{num(sum(t['seconds'] for t in played) / 3600)} h",
        ]
    )
    head = [
        "Model",
        "Per request, frame board",
        "Per request, macro board",
        "Real-time delay (steps)",
        "Test requests",
        "Test play time",
    ]
    return "Table 3: Time per request on the DGX Spark, and the test campaign\n\n" + table(head, rows, "lrrrrr")


def board_table(results: Results, board: str, number: int, caption: str) -> str:
    b = scores(results)["boards"][board]
    games = b["games"]
    rows = []
    for pid in ranked(b):
        p = b["players"][pid]
        rows.append(
            [title(pid), f"{num(p['index'])} {interval(p['index_ci'])}"]
            + [num(p["games"][g]["mean"], 2 if g == "connect4" else 1) for g in games]
        )
    for pid in ANCHORS:
        anchor = b["anchors"]
        rows.append(
            [f"*{pid}*", "0" if pid == "random" else "100"]
            + [num(anchor[g][pid], 2 if g == "connect4" else 1) for g in games]
        )
    head = ["Model", "Index [95% CI]"] + [SCORE_NAMES[g] for g in games]
    return f"Table {number}: {caption}\n\n" + table(head, rows, "lr" + "r" * len(games))


def table7(results: Results) -> str:
    b, frame = scores(results)["boards"]["realtime"], scores(results)["boards"]["frame"]
    k = delays(results)
    rows = []
    for pid in ranked(b):
        p = b["players"][pid]
        rows.append(
            [
                title(pid),
                span(k[pid]),
                num(frame["players"][pid]["index"]),
                f"{num(p['index'])} {interval(p['index_ci'])}",
            ]
            + [num(p["games"][g]["mean"], 2 if g == "tetris" else 1) for g in b["games"]]
        )
    head = ["Model", "Delay (steps)", "Frame index", "Real-time index [95% CI]"] + [SCORE_NAMES[g] for g in b["games"]]
    return "Table 7: The real-time board against the frame board\n\n" + table(
        head, rows, "lrrr" + "r" * len(b["games"])
    )


def snake_choices(results: Results, pid: str) -> tuple[int, int] | None:
    """(moves that end the game, decisions offering such a move next to a safe one) on the macro board."""
    games = decisions(results.suite() / "test" / "macro" / "snake" / pid, REPLAYS / "macro" / "snake" / pid)
    if games is None:
        return None
    picked = offered = 0
    for game in games:
        for d in game:
            if d.get("final") or d["forced"]:
                continue
            fatal = {o["key"] for o in d["options"] if o["text"].endswith(ENDS_GAME)}
            if fatal and len(fatal) < len(d["options"]):
                offered += 1
                picked += d["choice"] in fatal
    return picked, offered


def connect4_choices(results: Results) -> dict[str, tuple[int, int, int, int]] | None:
    """Per model in the direct games: (wins taken, wins on offer, fours allowed, decisions where one was avoidable)."""
    counts: dict[str, list[int]] = {}
    for pair in sorted((results.duel() / "test" / "direct" / "connect4").iterdir()):
        games = decisions(pair, REPLAYS / "duel" / pair.name)
        if games is None:
            return None
        for game in games:
            for d in game:
                if d.get("final") or d["forced"]:
                    continue
                c = counts.setdefault(d["player"], [0, 0, 0, 0])
                text = {o["key"]: o["text"] for o in d["options"]}
                wins = {k for k, t in text.items() if t.endswith(WINS)}
                gives = {k for k, t in text.items() if GIVES_FOUR in t}
                if wins:
                    c[0] += d["choice"] in wins
                    c[1] += 1
                if gives and len(gives) < len(text):
                    c[2] += d["choice"] in gives
                    c[3] += 1
    return {p: (c[0], c[1], c[2], c[3]) for p, c in counts.items()}


def table8(results: Results) -> str:
    c4 = connect4_choices(results)
    missing = "decision logs needed"
    rows = []
    for pid in [*models(), "random"]:
        agreement = (
            ""
            if pid == "random"
            else f"{num(100 * load(results.suite() / 'bias' / f'{pid}.json')['overall']['agreement'], 0)}%"
        )
        fatal = snake_choices(results, pid)
        taken = given = ""
        if pid != "random":
            taken = given = missing
            if c4 is not None:
                w, wo, g, go = c4[pid]
                taken, given = pct(w, wo), pct(g, go)
        name = title(pid) if pid != "random" else "*random*"
        rows.append([name, agreement, missing if fatal is None else pct(*fatal), taken, given])
    head = [
        "Model",
        "Same pick, options reversed",
        "Snake: picked a move that ends the game, a safe one on offer",
        "Connect Four: took a win on offer",
        "Connect Four: let the opponent complete four, when another move did not",
    ]
    return "Table 8: Acting on what the options say (exploratory)\n\n" + table(head, rows, "lrrrr")


def table9(results: Results) -> str:
    d = duel_scores(results)
    pairs_won: dict[str, int] = {}
    for record in d["pairs"].values():
        totals = {p: sum(o[p] for o in record["openings"].values()) for p in next(iter(record["openings"].values()))}
        best = max(totals.values())
        winners = [p for p, v in totals.items() if v == best]
        if len(winners) == 1:
            pairs_won[winners[0]] = pairs_won.get(winners[0], 0) + 1
    rows = []
    for pid, r in sorted(d["ratings"].items(), key=lambda x: -x[1]["elo"]):
        rows.append(
            [
                title(pid),
                f"{num(r['elo'], 0)} {interval(r['interval'], 0)}",
                num(r["points"]),
                str(pairs_won.get(pid, 0)),
                str(r["missed_wins"]),
                str(r["allowed_wins"]),
            ]
        )
    head = ["Model", "Elo [95% interval]", "Points of 360", "Pairs won of 9", "Missed wins", "Allowed fours"]
    return f"Table 9: Connect Four between the models ({d['games']:,} games)\n\n" + table(head, rows, "lrrrrr")


def pairs(results: Results) -> str:
    out = []
    for board in BOARDS:
        b = scores(results)["boards"][board]
        found = {(x["a"], x["b"]): x for x in b["pairs"]}
        order = ranked(b)
        out.append(f"{board}:")
        for i, a in enumerate(order):
            for other in order[i + 1 : i + 3]:
                if (a, other) in found:
                    x = found[(a, other)]
                    diff, ci = x["diff"], x["ci"]
                else:  # stored the other way round: flip the difference and its interval
                    x = found[(other, a)]
                    diff, ci = -x["diff"], [-x["ci"][1], -x["ci"][0]]
                out.append(f"  {title(a)} − {title(other)}: {num(diff, 2)} {interval(ci, 2)}, Holm p {x['p_holm']}")
    return "\n".join(out)


TABLES = {
    1: table1,
    3: table3,
    5: lambda r: board_table(r, "macro", 5, "The macro board, test seeds (mean raw score per game)"),
    6: lambda r: board_table(r, "frame", 6, "The frame board, test seeds (mean raw score per game)"),
    7: table7,
    8: table8,
    9: table9,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=ROOT / "results", help="the results directory")
    parser.add_argument("--tables", default=",".join(map(str, TABLES)), help="comma-separated table numbers")
    parser.add_argument("--pairs", action="store_true", help="print the adjacent pairs of each board instead")
    args = parser.parse_args()
    results = Results(args.results)
    if args.pairs:
        print(pairs(results))
        return
    for n in (int(x) for x in args.tables.split(",")):
        print(TABLES[n](results), end="\n\n")


if __name__ == "__main__":
    main()
