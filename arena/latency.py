"""Latency of one model, measured on the probe question sets of every game of the macro and frame boards.

Run it with that model alone on the GPU: busy neighbours slow every request (on the GB10 a model next to busy
servers measured 2.5 to 10 times slower). The file records the other GPU processes seen at the start, so a
contaminated measurement is visible. The real-time board reads the frame-board medians from here.
"""

from __future__ import annotations

import math
import platform
import shutil
import statistics
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from arena.client import DEFAULT_SERVER, ModelClient
from arena.core import JSON
from arena.logs import RESULTS, write_json
from arena.players import TextPlayer
from arena.probe import sample_questions
from arena.registry import contestants
from arena.runner import latency_path
from arena.suite import Suite


def gpu_processes() -> list[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def gpu_name() -> str | None:
    if shutil.which("nvidia-smi") is None:
        return None
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def measure(
    suite: Suite,
    player_id: str,
    *,
    server: str = DEFAULT_SERVER,
    sample: int = 200,
    warmup: int = 20,
    results: Path = RESULTS,
    progress: Callable[[str], None] = print,
) -> Path:
    contestant = contestants()[player_id]
    player = TextPlayer(contestant, ModelClient(server), suite.group_size)
    neighbours = gpu_processes()
    games: dict[str, JSON] = {}
    try:
        warm = sample_questions(suite, "macro", "snake", warmup)
        for question in warm:
            player.ask(question, "warmup")
        for board, game in suite.pairs():
            if suite.board(board).step_ms is not None:
                continue
            questions = sample_questions(suite, board, game, sample)
            times = [player.ask(question, "probe").latency_ms for question in questions]
            games[f"{board}/{game}"] = {
                "n": len(times),
                "median_ms": round(statistics.median(times), 3),
                "p95_ms": round(percentile(times, 0.95), 3),
                "mean_ms": round(statistics.fmean(times), 3),
            }
            progress(f"{player_id} {board}/{game}: median {games[f'{board}/{game}']['median_ms']:.1f} ms")
    finally:
        player.close()
    path = latency_path(suite.id, player_id, results)
    write_json(
        path,
        {
            "suite": suite.id,
            "player": player_id,
            "measured": datetime.now(UTC).isoformat(timespec="seconds"),
            "server": server,
            "warmup": warmup,
            "games": games,
            "environment": {
                "gpu": gpu_name(),
                "gpu_processes_at_start": neighbours,
                "machine": platform.machine(),
                "note": "client-side wall time per request, model-compose HTTP overhead included",
            },
        },
    )
    return path
