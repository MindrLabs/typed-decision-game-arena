"""Ask the models again: play seed 1 of every board and game through the model server, compare every decision with
the published log, and record what each model holds in memory while it plays.

    scripts/serve.sh                                         the model server, in another terminal
    uv run python scripts/recheck.py --out /tmp/recheck      every model, the fastest first
    uv run python scripts/recheck.py --out /tmp/recheck --models clef

The episodes go to --out, never to results/. For each model the script waits until no model holds the GPU, loads
the model with one request, plays seed 1 of every board and game with the arena's own runner,
and compares each decision with the published log in results/: the question, the order each request showed, every
pick and the probabilities, up to the first difference. Meanwhile it samples nvidia-smi every second for the GPU
memory of the model's runtime, and at the end reads the runtime's peak resident memory (VmHWM). The summary is
merged into results/v0.1/recheck.json, so models can be checked in separate runs.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arena.client import DEFAULT_SERVER, ModelClient
from arena.environment import runtime_packages
from arena.gpu import gpu_processes
from arena.players import TextPlayer
from arena.probe import sample_questions
from arena.registry import contestants
from arena.runner import run
from arena.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SEED = 1
# The order of a campaign: the fastest models first, Clef last on a freshly started server (docs/operations.md).
ORDER = (
    "laya-multilingual",
    "laya-english",
    "laya-typed",
    "kev-0.8b",
    "clef-flash",
    "kev-4b",
    "nimble-v2",
    "nimble",
    "kev-9b",
    "clef",
)
HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"


class Sampler(threading.Thread):
    """The largest GPU memory nvidia-smi reports for one model's runtime, sampled every `period` seconds."""

    def __init__(self, player: str, period: float = 1.0) -> None:
        super().__init__(daemon=True)
        self.player, self.period = player, period
        self.peak_mib = 0
        self.pid: int | None = None
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.is_set():
            for process in gpu_processes():
                if process.runtime == self.player and process.memory_mib is not None:
                    self.peak_mib = max(self.peak_mib, process.memory_mib)
                    self.pid = process.pid
            self._done.wait(self.period)

    def stop(self) -> None:
        self._done.set()
        self.join()


def peak_resident_mib(pid: int | None) -> int | None:
    """The process's peak resident set size since it started (VmHWM), in MiB."""
    if pid is None:
        return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None


def wait_for_gpu(timeout: float = 900.0) -> None:
    """Until no model's runtime holds more than an idle CUDA context, so that every model starts cold and alone
    (model-compose unloads a model after 2 idle minutes)."""
    deadline = time.monotonic() + timeout
    while True:
        loaded = sorted({p.runtime for p in gpu_processes() if p.runtime and p.busy})
        if not loaded:
            return
        if time.monotonic() > deadline:
            raise TimeoutError(f"{', '.join(loaded)} stayed loaded; stop them first")
        time.sleep(5)


def read_log(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def compare(published: list[dict[str, Any]], rerun: list[dict[str, Any]]) -> dict[str, Any]:
    """Decision by decision up to the first difference: the question, each request's shown order and pick, and the
    probabilities, which may differ in the last digits without changing a pick."""
    first: dict[str, Any] | None = None
    largest = 0.0
    same = 0
    for i, (a, b) in enumerate(zip(published, rerun, strict=False)):
        if a.get("final") or b.get("final"):
            if a != b:
                first = {"decision": i, "what": "end"}
            break
        if (a["state"], a["instructions"], a["options"]) != (b["state"], b["instructions"], b["options"]):
            first = {"decision": i, "what": "question"}
            break
        if [(c["stage"], c["keys"]) for c in a["calls"]] != [(c["stage"], c["keys"]) for c in b["calls"]]:
            first = {"decision": i, "what": "requests"}
            break
        for x, y in zip(a["calls"], b["calls"], strict=True):
            if x["p"] and y["p"]:
                largest = max(largest, *(abs(x["p"][k] - y["p"][k]) for k in x["p"]))
        if [c["choice"] for c in a["calls"]] != [c["choice"] for c in b["calls"]] or a["choice"] != b["choice"]:
            first = {"decision": i, "what": "pick", "published": a["choice"], "rerun": b["choice"]}
            break
        same += 1
    if first is None and len(published) != len(rerun):
        first = {"decision": min(len(published), len(rerun)), "what": "length"}
    decisions = sum(1 for d in published if not d.get("final"))
    return {
        "decisions": decisions,
        "same_before_first_difference": same,
        "identical": first is None,
        "first_difference": first,
        "largest_probability_difference": round(largest, 9),
    }


def snapshot(repository: str) -> str | None:
    """The commit the local Hugging Face cache resolves `main` to, for a repository model-compose does not pin."""
    ref = HF_HUB / f"models--{repository.replace('/', '--')}" / "refs" / "main"
    return ref.read_text().strip() if ref.exists() else None


def check(player: str, out: Path, server: str) -> dict[str, Any]:
    suite = load_suite("v0.1")
    contestant = contestants()[player]
    wait_for_gpu()
    sampler = Sampler(player)
    sampler.start()
    # Load the model with one patient request: the runner's requests give up after 15 minutes.
    loader = TextPlayer(contestant, ModelClient(server, timeout=3600.0, retries=0), suite.group_size)
    try:
        loader.ask(sample_questions(suite, "macro", "tetris", 1)[0], "load")
    finally:
        loader.close()
    games: dict[str, Any] = {}
    for board, game in suite.pairs():
        summary = run(suite, board, game, player, [SEED], seed_set="test", server=server, results=out)
        key = f"{board}/{game}"
        if summary.failed:
            games[key] = {"error": summary.failed[0].get("error")}
            continue
        published = RESULTS / suite.id / "test" / board / game / player
        rerun = out / suite.id / "test" / board / game / player
        result = compare(
            read_log(published / "decisions" / f"{SEED}.jsonl.gz"), read_log(rerun / "decisions" / f"{SEED}.jsonl.gz")
        )
        lines = (published / "episodes.jsonl").read_text().splitlines()
        episode = next(e for e in map(json.loads, lines) if e["seed"] == SEED)
        again = json.loads((rerun / "episodes.jsonl").read_text().splitlines()[-1])
        result["score"] = {"published": episode["score"], "rerun": again["score"]}
        games[key] = result
    sampler.stop()
    return {
        "gpu_memory_mib": sampler.peak_mib or None,
        "peak_resident_mib": peak_resident_mib(sampler.pid),
        "revision": contestant.revision or snapshot(contestant.repository or ""),
        "games": games,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="results directory for the new episodes")
    parser.add_argument("--models", default=",".join(ORDER), help="comma-separated players, in this order")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    args = parser.parse_args()
    # The real-time board needs each model's latency under the current lock: the published one, so that every
    # model answers with the delay its published games had.
    latency = args.out / "v0.1" / "latency"
    latency.mkdir(parents=True, exist_ok=True)
    for path in (RESULTS / "v0.1" / "latency").glob("*.json"):
        shutil.copy2(path, latency / path.name)
    summary_path = RESULTS / "v0.1" / "recheck.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {"seed": SEED, "models": {}}
    published_packages = json.loads((RESULTS / "v0.1" / "environment.json").read_text())["runtimes"]
    packages = runtime_packages()
    for player in args.models.split(","):
        print(f"{player}: checking seed {SEED}", flush=True)
        result = check(player, args.out, args.server)
        result["same_packages"] = packages.get(player) == published_packages.get(player)
        result["checked"] = datetime.now(UTC).isoformat(timespec="seconds")
        summary["models"][player] = result
        summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        same = sum(g.get("identical", False) for g in result["games"].values())
        print(
            f"{player}: {same} of {len(result['games'])} games identical, "
            f"GPU {result['gpu_memory_mib']} MiB, peak resident {result['peak_resident_mib']} MiB",
            flush=True,
        )


if __name__ == "__main__":
    main()
