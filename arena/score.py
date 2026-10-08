"""Scores: per-game means, normalised scores, board indices, confidence intervals and pairwise comparisons.

For one game, `k = clip((mean - random) / (reference - random), 0, 1)`, where `random` and `reference` are the
anchors' mean scores on the same seeds. A board's index is 100 x the mean of `k` over its games (equal weights).
The real-time board takes its anchors from the frame board: random play, and the reference reacting instantly.

Intervals come from a paired bootstrap: each replicate resamples the seeds of every game once and applies that
same resample to every player and both anchors, then recomputes everything. The resample indices come from the
arena's own seeded stream, so a report is reproducible to the last digit. Pairwise differences between complete
players get two-sided bootstrap p-values, adjusted with Holm's method within each board.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from arena.core import JSON
from arena.logs import RESULTS, read_episodes
from arena.registry import BASELINES
from arena.seeding import Rng
from arena.suite import Suite, locked_digest

type Matrix = npt.NDArray[np.float64]


class StaleResultsError(ValueError):
    """Test-seed episodes recorded under a different suite lock than the current one."""


@dataclass(frozen=True)
class GameData:
    seeds: list[int]
    scores: dict[str, dict[int, float]]  # player -> seed -> score
    episodes: dict[str, list[JSON]]


def load_game(suite: Suite, seed_set: str, board: str, game: str, results: Path = RESULTS) -> GameData:
    """Episodes of every player for one game. Test-seed episodes must carry the current suite lock."""
    seeds = suite.game(board, game).seeds[seed_set]
    directory = results / suite.id / seed_set / board / game
    lock = locked_digest(suite) if seed_set == "test" else None
    scores: dict[str, dict[int, float]] = {}
    episodes: dict[str, list[JSON]] = {}
    if directory.exists():
        for player_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
            items = [e for e in read_episodes(player_dir) if int(e["seed"]) in seeds]
            stale = sorted(int(e["seed"]) for e in items if e.get("lock") != lock)
            if seed_set == "test" and stale:
                raise StaleResultsError(
                    f"{player_dir}: seeds {stale} were recorded under another suite lock; remove them and rerun"
                )
            if items:
                episodes[player_dir.name] = items
                scores[player_dir.name] = {int(e["seed"]): float(e["score"]) for e in items}
    return GameData(seeds, scores, episodes)


def bootstrap_indices(n: int, replicates: int, *parts: str | int) -> npt.NDArray[np.int64]:
    rng = Rng.derive("bootstrap", *parts)
    return np.array([[rng.below(n) for _ in range(n)] for _ in range(replicates)], dtype=np.int64)


def normalise(mean: Matrix | float, low: Matrix | float, high: Matrix | float) -> Matrix:
    span = np.asarray(high, dtype=np.float64) - np.asarray(low, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = (np.asarray(mean, dtype=np.float64) - low) / span
    k = np.where(np.abs(span) < 1e-12, np.nan, k)
    return np.clip(k, 0.0, 1.0)


def interval(values: Matrix, confidence: float) -> list[float] | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    tail = (1 - confidence) / 2 * 100
    low, high = np.percentile(finite, [tail, 100 - tail])
    return [round(float(low), 4), round(float(high), 4)]


def holm(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def summarise_metrics(episodes: list[JSON]) -> JSON:
    """Means of numeric metrics (booleans as rates), counts of categorical ones."""
    numeric: dict[str, list[float]] = {}
    counts: dict[str, dict[str, int]] = {}
    for episode in episodes:
        for name, value in episode.get("metrics", {}).items():
            if isinstance(value, bool | int | float):
                numeric.setdefault(name, []).append(float(value))
            else:
                bucket = counts.setdefault(name, {})
                bucket[str(value)] = bucket.get(str(value), 0) + 1
    out: JSON = {name: round(sum(v) / len(v), 4) for name, v in numeric.items()}
    out.update(counts)
    return out


def _latency(episodes: list[JSON]) -> JSON | None:
    medians = [e["latency_ms"]["median"] for e in episodes if e.get("latency_ms")]
    if not medians:
        return None
    return {"median_of_episode_medians": round(float(np.median(medians)), 3), "episodes": len(medians)}


@dataclass(frozen=True)
class Anchors:
    low: Matrix  # random play, per seed
    high: Matrix  # the reference player, per seed


def _anchors(data: GameData, seeds: list[int]) -> Anchors | None:
    low, high = data.scores.get("random", {}), data.scores.get("reference", {})
    if not all(s in low and s in high for s in seeds):
        return None
    return Anchors(np.array([low[s] for s in seeds]), np.array([high[s] for s in seeds]))


def _game_entry(
    have: dict[int, float],
    seeds: list[int],
    draws: npt.NDArray[np.int64],
    *,
    anchors: Anchors | None,
    episodes: list[JSON],
    confidence: float,
) -> tuple[JSON, Matrix | None]:
    """One player's numbers for one game, and the bootstrap draws of its normalised score (when complete)."""
    got = [s for s in seeds if s in have]
    entry: JSON = {"n": len(got)}
    if not got:
        return entry, None
    values = np.array([have[s] for s in got])
    entry["mean"] = round(float(values.mean()), 4)
    entry["metrics"] = summarise_metrics(episodes)
    latency = _latency(episodes)
    if latency:
        entry["latency_ms"] = latency
    if len(got) < len(seeds):
        return entry, None
    means = values[draws].mean(axis=1)
    entry["mean_ci"] = interval(means, confidence)
    if anchors is None:
        return entry, None
    k = float(normalise(values.mean(), anchors.low.mean(), anchors.high.mean()))
    k_draws = normalise(means, anchors.low[draws].mean(axis=1), anchors.high[draws].mean(axis=1))
    entry["k"] = None if np.isnan(k) else round(k, 4)
    entry["k_ci"] = interval(k_draws, confidence)
    return entry, k_draws


def _pairs(
    ranked: list[str], players: dict[str, JSON], index_draws: dict[str, Matrix], confidence: float
) -> list[JSON]:
    models = [p for p in ranked if p not in BASELINES]
    pairs: list[JSON] = []
    raw: list[float] = []
    for i, a in enumerate(models):
        for b in models[i + 1 :]:
            diff = 100 * (index_draws[a] - index_draws[b])
            diff = diff[np.isfinite(diff)]
            below, above = int((diff <= 0).sum()), int((diff >= 0).sum())
            p_value = min(1.0, 2 * (min(below, above) + 1) / (diff.size + 1))
            raw.append(p_value)
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "diff": round(players[a]["index"] - players[b]["index"], 2),
                    "ci": interval(diff, confidence),
                    "p": round(p_value, 4),
                }
            )
    for pair, adjusted in zip(pairs, holm(raw), strict=True):
        pair["p_holm"] = round(adjusted, 4)
    return pairs


def score_board(suite: Suite, seed_set: str, board: str, results: Path = RESULTS) -> JSON:
    spec = suite.board(board)
    anchor_board = spec.based_on or board
    games = list(spec.games)
    data = {g: load_game(suite, seed_set, board, g, results) for g in games}
    anchors = {g: _anchors(load_game(suite, seed_set, anchor_board, g, results), data[g].seeds) for g in games}

    anchor_report: JSON = {}
    for g in games:
        a = anchors[g]
        anchor_report[g] = {"n": len(data[g].seeds)}
        if a is not None:
            anchor_report[g].update(
                {"random": round(float(a.low.mean()), 4), "reference": round(float(a.high.mean()), 4)}
            )
    missing = [f"{anchor_board}/{g}" for g in games if anchors[g] is None]

    baselines_here = set() if spec.based_on else set(BASELINES)
    players = sorted(
        {p for g in games for p in data[g].scores if p not in BASELINES}
        | (baselines_here & {p for g in games for p in data[g].scores})
    )
    report: dict[str, JSON] = {p: {"games": {}} for p in players}
    k_draws: dict[str, list[Matrix]] = {p: [] for p in players}
    for g in games:
        draws = bootstrap_indices(len(data[g].seeds), suite.bootstrap, suite.id, seed_set, board, g)
        for p in players:
            entry, draws_k = _game_entry(
                data[g].scores.get(p, {}),
                data[g].seeds,
                draws,
                anchors=anchors[g],
                episodes=data[g].episodes.get(p, []),
                confidence=suite.confidence,
            )
            report[p]["games"][g] = entry
            if draws_k is not None:
                k_draws[p].append(draws_k)

    index_draws: dict[str, Matrix] = {}
    for p in players:
        info = report[p]
        info["complete"] = all(info["games"][g]["n"] == len(data[g].seeds) for g in games)
        ks = [info["games"][g].get("k") for g in games]
        if info["complete"] and len(k_draws[p]) == len(games) and all(k is not None for k in ks):
            index_draws[p] = np.nanmean(np.vstack(k_draws[p]), axis=0)
            info["index"] = round(100 * float(np.mean([float(k) for k in ks if k is not None])), 2)
            ci = interval(index_draws[p], suite.confidence)
            info["index_ci"] = [round(100 * x, 2) for x in ci] if ci else None
    ranked = sorted(index_draws, key=lambda p: -float(report[p]["index"]))
    for rank, p in enumerate(ranked, 1):
        report[p]["rank"] = rank

    return {
        "board": board,
        "anchor_board": anchor_board,
        "games": games,
        "anchors": anchor_report,
        "missing_anchors": missing,
        "players": report,
        "ranking": ranked,
        "pairs": _pairs(ranked, report, index_draws, suite.confidence),
    }


def score(suite: Suite, seed_set: str, results: Path = RESULTS) -> JSON:
    boards = sorted(suite.boards.values(), key=lambda b: b.order)
    report: dict[str, Any] = {
        "suite": suite.id,
        "seed_set": seed_set,
        "lock": locked_digest(suite) if seed_set == "test" else None,
        "bootstrap": suite.bootstrap,
        "confidence": suite.confidence,
        "boards": {b.id: score_board(suite, seed_set, b.id, results) for b in boards},
    }
    return report
