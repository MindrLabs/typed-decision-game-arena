"""`arena campaign`: every run of a seed set in the documented order, unattended and resumable.

1. Anchors: random and reference on every turn-based board (CPU only, in parallel processes).
2. Each model in turn, so that one model at a time works on the GPU: one question per game first (a model that
   cannot answer is reported and skipped at once, not retried episode by episode); its turn-based boards; its
   latency, once no other model holds the GPU; its real-time board, which needs that latency; its position bias.

Nothing is done twice. The runner skips episodes that are already logged, and latency and bias are measured only
when no file for the current suite lock exists. Failed episodes run again, up to `attempts` times in all. Before
each step of a model the campaign waits for the model server, so a server that restarts delays the campaign
instead of failing it; a server that stays away longer than `server_wait` stops the campaign. A step that still
fails is reported and the campaign moves on (a real-time board without its latency is skipped), so one broken
model does not hold up the others; running the same command again picks up whatever is left.

`arena status` reads the same result files and shows what is complete.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from arena import bias, latency, logs
from arena.bias import bias_path
from arena.client import DEFAULT_SERVER, ModelClient
from arena.core import PlayerError
from arena.gpu import GpuProcess, gpu_processes, gpu_utilization
from arena.logs import RESULTS, read_episodes, read_json, run_dir
from arena.players import TextPlayer
from arena.probe import smoke
from arena.registry import BASELINES, contestants
from arena.runner import SuiteNotFrozenError, latency_path
from arena.runner import run as run_episodes
from arena.suite import Suite, lock_differences, locked_digest

type Say = Callable[[str], None]


class ServerUnavailableError(RuntimeError):
    """The model server did not answer for longer than the campaign waits."""


class GpuBusyError(RuntimeError):
    """Another process kept working on the GPU for longer than a latency measurement waits."""


@dataclass
class Report:
    failed: list[str] = field(default_factory=list)


def measured(path: Path, lock: str | None) -> bool:
    """A latency or bias file exists for the current suite lock."""
    return path.exists() and read_json(path).get("lock") == lock


def wait_for_server(
    server: str,
    player: str,
    timeout: float,
    *,
    say: Say,
    poll: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Until the model server answers and serves `player`. A server that answers without serving it is a setup
    error, reported at once."""
    client = ModelClient(server, retries=0, timeout=10.0)
    deadline = clock() + timeout
    waiting = False
    try:
        while True:
            try:
                served = client.workflows()
            except httpx.HTTPError as error:
                if clock() >= deadline:
                    raise ServerUnavailableError(f"no model server at {server} for {timeout:.0f}s: {error}") from None
                if not waiting:
                    say(f"waiting for the model server at {server} ({type(error).__name__})")
                    waiting = True
                sleep(poll)
                continue
            if player not in served:
                raise PlayerError(f"{player} is not served at {server}; serving: {', '.join(served)}")
            if waiting:
                say(f"the model server at {server} is back")
            return
    finally:
        client.close()


QUIET_PERCENT = 5
QUIET_SAMPLES = 10


def wait_for_quiet_gpu(
    player: str,
    timeout: float,
    *,
    say: Say,
    utilization: Callable[[], int | None] = gpu_utilization,
    processes: Callable[[], list[GpuProcess]] = gpu_processes,
    poll: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Until nothing else computes on the GPU: its utilisation stays at most QUIET_PERCENT for QUIET_SAMPLES
    one-second samples (the campaign sends no requests meanwhile). Where utilisation is not reported, until no
    process other than the player's own runtime holds more than an idle context."""
    deadline = clock() + timeout
    waiting = False
    while True:
        samples: list[int] = []
        for _ in range(QUIET_SAMPLES):
            value = utilization()
            if value is None:
                break
            samples.append(value)
            if value > QUIET_PERCENT:
                break
            sleep(1.0)
        if len(samples) == QUIET_SAMPLES:
            return
        if samples:
            reason = f"utilisation {samples[-1]}%"
        else:
            busy = [p for p in processes() if p.busy and p.runtime != player]
            if not busy:
                return
            reason = ", ".join(p.label for p in busy)
        if clock() >= deadline:
            raise GpuBusyError(f"the GPU stayed busy for {timeout:.0f}s ({reason})")
        if not waiting:
            say(f"latency of {player} waits for the GPU ({reason})")
            waiting = True
        sleep(poll)


@dataclass
class Campaign:
    suite: Suite
    seed_set: str
    server: str = DEFAULT_SERVER
    results: Path = RESULTS
    anchor_workers: int = 8
    attempts: int = 3
    server_wait: float = 3600.0
    gpu_wait: float = 1800.0
    latency_sample: int = 200
    bias_sample: int = 40
    say: Say = logs.say
    utilization: Callable[[], int | None] = gpu_utilization
    processes: Callable[[], list[GpuProcess]] = gpu_processes
    report: Report = field(default_factory=Report)

    def turn_based(self) -> list[str]:
        return [b.id for b in sorted(self.suite.boards.values(), key=lambda b: b.order) if b.step_ms is None]

    def real_time(self) -> list[str]:
        return [b.id for b in sorted(self.suite.boards.values(), key=lambda b: b.order) if b.step_ms is not None]

    def board(self, player: str, board: str, *, workers: int = 1) -> None:
        """Every game of one board, failed episodes retried; what still fails goes into the report."""
        for game, spec in self.suite.board(board).games.items():
            failed = 0
            for attempt in range(1, self.attempts + 1):
                if player not in BASELINES:
                    wait_for_server(self.server, player, self.server_wait, say=self.say)
                summary = run_episodes(
                    self.suite,
                    board,
                    game,
                    player,
                    spec.seeds[self.seed_set],
                    seed_set=self.seed_set,
                    server=self.server,
                    workers=workers,
                    results=self.results,
                    progress=self.say,
                )
                failed = len(summary.failed)
                if not failed:
                    break
                self.say(f"{board}/{game} {player}: {failed} episodes failed (attempt {attempt} of {self.attempts})")
            if failed:
                self.report.failed.append(f"{board}/{game} {player}: {failed} episodes still fail")

    def diagnostic(self, kind: Literal["latency", "bias"], player: str) -> bool:
        """Latency or bias, unless a file for the current lock exists. False when it could not be measured."""
        path = (latency_path if kind == "latency" else bias_path)(self.suite.id, player, self.results)
        if measured(path, locked_digest(self.suite)):
            return True
        try:
            wait_for_server(self.server, player, self.server_wait, say=self.say)
            if kind == "latency":
                wait_for_quiet_gpu(
                    player, self.gpu_wait, say=self.say, utilization=self.utilization, processes=self.processes
                )
                latency.measure(
                    self.suite,
                    player,
                    server=self.server,
                    sample=self.latency_sample,
                    results=self.results,
                    progress=self.say,
                )
            else:
                bias.measure(
                    self.suite,
                    player,
                    server=self.server,
                    sample=self.bias_sample,
                    results=self.results,
                    progress=self.say,
                )
        except (PlayerError, GpuBusyError) as error:
            self.report.failed.append(f"{kind} {player}: {error}")
            return False
        return True

    def answers(self, player: str) -> bool:
        """One question per game; False (and reported) when the model cannot answer one of them."""
        wait_for_server(self.server, player, self.server_wait, say=self.say)
        model = TextPlayer(contestants()[player], ModelClient(self.server), self.suite.group_size)
        try:
            for board, game, answer in smoke(self.suite, model):
                if isinstance(answer, PlayerError):
                    self.report.failed.append(f"{player}: no answer on {board}/{game}, skipped: {answer}")
                    return False
        finally:
            model.close()
        return True

    def model(self, player: str) -> None:
        self.say(f"== {player}")
        try:
            if not self.answers(player):
                return
            for board in self.turn_based():
                self.board(player, board)
            timed = self.diagnostic("latency", player)
            for board in self.real_time():
                if timed:
                    self.board(player, board)
                else:
                    self.report.failed.append(f"{board} {player}: skipped, no latency")
            self.diagnostic("bias", player)
        except PlayerError as error:  # not served at all: nothing of this player can run
            self.report.failed.append(f"{player}: {error}")

    def run(self, models: Sequence[str], *, anchors: bool = True) -> Report:
        known = contestants()
        unknown = [m for m in models if m not in known]
        if unknown:
            raise KeyError(f"unknown models {unknown}; models: {sorted(known)} (the anchors run on their own)")
        if self.seed_set == "test":
            problems = lock_differences(self.suite)
            if problems:
                raise SuiteNotFrozenError(
                    "test seeds need a frozen suite matching this tree:\n  " + "\n  ".join(problems)
                )
        if anchors:
            self.say("== anchors")
            for board in self.turn_based():
                for baseline in BASELINES:
                    self.board(baseline, board, workers=self.anchor_workers)
        for model in models:
            self.model(model)
        self.say(
            "campaign complete"
            if not self.report.failed
            else "campaign finished with steps left:\n  " + "\n  ".join(self.report.failed)
        )
        return self.report


# --- status -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Progress:
    player: str
    boards: dict[str, tuple[int, int] | None]  # board -> (episodes done, episodes in the seed set); None: n/a
    latency: bool | None  # None for the anchors
    bias: bool | None


def status(suite: Suite, seed_set: str, results: Path = RESULTS) -> list[Progress]:
    """What is complete, per player and board. Test-seed episodes count only under the current suite lock."""
    lock = locked_digest(suite)
    rows: list[Progress] = []
    for player in [*BASELINES, *contestants()]:
        boards: dict[str, tuple[int, int] | None] = {}
        for spec in sorted(suite.boards.values(), key=lambda b: b.order):
            if player in BASELINES and spec.step_ms is not None:
                boards[spec.id] = None
                continue
            done = expected = 0
            for game, game_spec in spec.games.items():
                seeds = set(game_spec.seeds[seed_set])
                episodes = read_episodes(run_dir(suite.id, seed_set, spec.id, game, player, results=results))
                fresh = {int(e["seed"]) for e in episodes if seed_set != "test" or e.get("lock") == lock}
                done += len(fresh & seeds)
                expected += len(seeds)
            boards[spec.id] = (done, expected)
        model = player not in BASELINES
        rows.append(
            Progress(
                player,
                boards,
                measured(latency_path(suite.id, player, results), lock) if model else None,
                measured(bias_path(suite.id, player, results), lock) if model else None,
            )
        )
    return rows


def format_status(rows: list[Progress]) -> str:
    if not rows:
        return ""
    boards = list(rows[0].boards)

    def cell(value: tuple[int, int] | None) -> str:
        return "-" if value is None else f"{value[0]}/{value[1]}"

    def flag(value: bool | None) -> str:
        return "-" if value is None else ("yes" if value else "no")

    header = f"{'player':<18} " + " ".join(f"{b:>9}" for b in boards) + f" {'latency':>8} {'bias':>5}"
    body = [
        f"{row.player:<18} "
        + " ".join(f"{cell(row.boards[b]):>9}" for b in boards)
        + f" {flag(row.latency):>8} {flag(row.bias):>5}"
        for row in rows
    ]
    return "\n".join([header, *body])
