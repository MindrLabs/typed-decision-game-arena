"""Run episodes of one (board, game, player) over a seed list: resumable, optionally in parallel processes.

Seeds that already have an episode line are skipped, so re-running the same command continues an interrupted
run. A failed episode (server down, malformed answer) is written to errors.jsonl and simply runs again next
time; its partial decision log is discarded. Test seeds need a frozen suite whose lock matches the tree.
"""

from __future__ import annotations

import math
import multiprocessing
import statistics
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from arena import __version__
from arena.client import DEFAULT_SERVER, ModelClient
from arena.core import JSON, Player
from arena.episode import DecisionRecord, play
from arena.logs import (
    RESULTS,
    DecisionWriter,
    append_jsonl,
    decisions_path,
    episodes_path,
    read_episodes,
    read_json,
    run_dir,
)
from arena.players import RandomPlayer, ReferencePlayer, TextPlayer
from arena.registry import BASELINES, contestants
from arena.suite import Suite, load_suite, lock_differences, locked_digest
from arena.tasks import make_task


class SuiteNotFrozenError(RuntimeError):
    pass


class LatencyMissingError(RuntimeError):
    pass


def make_player(player_id: str, suite: Suite, board: str, game: str, server: str) -> Player:
    if player_id == "random":
        return RandomPlayer()
    if player_id == "reference":
        spec = suite.game(board, game)
        return ReferencePlayer(game, spec.track, dict(spec.reference))
    known = contestants()
    if player_id not in known:
        raise KeyError(f"unknown player {player_id!r}; baselines {BASELINES}, models {sorted(known)}")
    return TextPlayer(known[player_id], ModelClient(server), suite.group_size)


def latency_path(suite_id: str, player_id: str, results: Path = RESULTS) -> Path:
    return results / suite_id / "latency" / f"{player_id}.json"


def delay_steps(suite: Suite, board: str, game: str, player_id: str, results: Path = RESULTS) -> int:
    """Reaction time in steps on the real-time board (0 elsewhere): the player's measured median latency on the
    same game's frame board, rounded up to whole steps, at least one. The real-time board has no baseline runs:
    its anchors are the frame board's (random play, and the reference reacting instantly)."""
    spec = suite.board(board)
    if spec.step_ms is None:
        return 0
    if player_id in BASELINES:
        raise ValueError(f"baselines do not run on the {board} board; its anchors are the {spec.based_on} board's")
    path = latency_path(suite.id, player_id, results)
    key = f"{spec.based_on}/{game}"
    games = read_json(path).get("games", {}) if path.exists() else {}
    if key not in games:
        hint = f"run `arena latency --player {player_id}` first"
        raise LatencyMissingError(f"no latency for {player_id} on {key}; {hint}")
    return max(1, math.ceil(float(games[key]["median_ms"]) / spec.step_ms))


@dataclass(frozen=True)
class Job:
    suite_id: str
    seed_set: str
    board: str
    game: str
    player: str
    seed: int
    server: str
    delay_steps: int
    results: str
    lock: str | None


def _model_info(player_id: str) -> JSON | None:
    if player_id in BASELINES:
        return None
    c = contestants()[player_id]
    return {
        "family": c.family,
        "repository": c.repository,
        "revision": c.revision,
        "base_model": c.base_model,
        "preset": c.preset,
        "config_sha": c.config_sha,
    }


def run_job(job: Job) -> tuple[JSON | None, JSON | None]:
    """Play one episode. Returns (episode line, None) or (None, error line)."""
    suite = load_suite(job.suite_id)
    task = make_task(suite, job.board, job.game)
    player = make_player(job.player, suite, job.board, job.game, job.server)
    directory = run_dir(job.suite_id, job.seed_set, job.board, job.game, job.player, results=Path(job.results))
    writer = DecisionWriter(decisions_path(directory, job.seed))
    latencies: list[float] = []

    def record(item: DecisionRecord) -> None:
        latencies.extend(call.latency_ms for call in item.decision.calls)
        writer.write(item)

    started = datetime.now(UTC)
    clock = time.perf_counter()
    base: JSON = {
        "suite": job.suite_id,
        "lock": job.lock,
        "seed_set": job.seed_set,
        "board": job.board,
        "game": job.game,
        "player": job.player,
        "seed": job.seed,
        "started": started.isoformat(timespec="seconds"),
    }
    try:
        outcome = play(
            task,
            player,
            job.seed,
            suite_id=job.suite_id,
            board=job.board,
            delay_steps=job.delay_steps,
            on_decision=record,
        )
        writer.finish(task.snapshot(), task.steps)
        writer.commit()
    except Exception as error:  # an episode failure must not stop the other seeds
        writer.discard()
        return None, {**base, "error": f"{type(error).__name__}: {error}"}
    finally:
        player.close()
        task.close()
    latency = None
    if latencies:
        ordered = sorted(latencies)
        latency = {
            "median": round(statistics.median(ordered), 3),
            "p95": round(ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)], 3),
            "n": len(ordered),
        }
    episode = {
        **base,
        "score": outcome.score,
        "metrics": outcome.metrics,
        "decisions": outcome.decisions,
        "forced": outcome.forced,
        "calls": outcome.calls,
        "steps": outcome.steps,
        "delay_steps": job.delay_steps,
        "latency_ms": latency,
        "model": _model_info(job.player),
        "arena": __version__,
        "seconds": round(time.perf_counter() - clock, 3),
    }
    return episode, None


@dataclass
class Summary:
    finished: list[JSON] = field(default_factory=list)
    failed: list[JSON] = field(default_factory=list)
    skipped: int = 0


def run(
    suite: Suite,
    board: str,
    game: str,
    player_id: str,
    seeds: list[int],
    *,
    seed_set: str,
    server: str = DEFAULT_SERVER,
    workers: int = 1,
    results: Path = RESULTS,
    progress: Callable[[str], None] | None = None,
) -> Summary:
    say = progress or (lambda line: print(line, file=sys.stderr, flush=True))
    if seed_set == "test":
        problems = lock_differences(suite)
        if problems:
            raise SuiteNotFrozenError("test seeds need a frozen suite matching this tree:\n  " + "\n  ".join(problems))
    elif seed_set != "dev":
        raise ValueError(f"seed set must be 'dev' or 'test', got {seed_set!r}")
    suite.game(board, game)  # fail early on a typo
    if player_id not in BASELINES and player_id not in contestants():
        raise KeyError(f"unknown player {player_id!r}; baselines {BASELINES}, models {sorted(contestants())}")
    delay = delay_steps(suite, board, game, player_id, results)
    directory = run_dir(suite.id, seed_set, board, game, player_id, results=results)
    done = {int(e["seed"]) for e in read_episodes(directory)}
    todo = [seed for seed in seeds if seed not in done]
    summary = Summary(skipped=len(seeds) - len(todo))
    lock = locked_digest(suite) if seed_set == "test" else None
    jobs = [Job(suite.id, seed_set, board, game, player_id, seed, server, delay, str(results), lock) for seed in todo]

    def handle(episode: JSON | None, error: JSON | None) -> None:
        if episode is not None:
            append_jsonl(episodes_path(directory), episode)
            summary.finished.append(episode)
            say(
                f"{board}/{game} {player_id} seed {episode['seed']}: score {episode['score']:g} "
                f"({episode['decisions']} decisions, {episode['calls']} requests, {episode['seconds']:.1f}s)"
            )
        if error is not None:
            append_jsonl(directory / "errors.jsonl", error)
            summary.failed.append(error)
            say(f"{board}/{game} {player_id} seed {error['seed']}: FAILED {error['error']}")

    if workers > 1 and player_id not in BASELINES:
        say(
            f"note: {workers} workers share one model server; per-request latency in these episodes includes "
            "queueing (the real-time board uses `arena latency`, not these numbers)"
        )
    if workers <= 1:
        for job in jobs:
            handle(*run_job(job))
    else:
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            futures = [pool.submit(run_job, job) for job in jobs]
            for future in as_completed(futures):
                handle(*future.result())
    return summary
