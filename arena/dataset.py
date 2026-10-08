"""`arena dataset`: publish the results of a seed set as a Hugging Face dataset.

Git keeps the episode lines and scores. The decision logs (every request with its shown order, choice and
probabilities, and a snapshot of every position) are far too many for git, so they go to a dataset repository
together with everything needed to read and check them: the suite and its lock, the episode lines, latency,
bias, the environment record and the scores. One upload is one commit, and files of earlier uploads of the same
seed set that are no longer in the results are removed in that commit, so every dataset revision holds exactly
one consistent set of results. A new repository is created private; visibility is never changed here.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from arena.core import JSON
from arena.logs import RESULTS, decisions_path, read_episodes, read_json, write_json
from arena.score import StaleResultsError, score
from arena.suite import ROOT, Suite, locked_digest

GITHUB = "https://github.com/MindrLabs/typed-decision-game-arena"


class Hub(Protocol):
    """The two calls of `huggingface_hub.HfApi` this module uses."""

    def create_repo(self, repo_id: str, *, repo_type: str, private: bool, exist_ok: bool) -> Any: ...

    def upload_folder(
        self,
        *,
        repo_id: str,
        folder_path: str | Path,
        repo_type: str,
        commit_message: str,
        delete_patterns: list[str],
    ) -> Any: ...


def _place(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)  # no copy of gigabytes of logs when staging on the same disk
    except OSError:
        shutil.copy2(source, target)


def _episode_dirs(suite: Suite, seed_set: str, results: Path) -> Iterator[Path]:
    for board, game in suite.pairs():
        game_dir = results / suite.id / seed_set / board / game
        if game_dir.exists():
            yield from sorted(p for p in game_dir.iterdir() if p.is_dir())


def stage(suite: Suite, seed_set: str, into: Path, results: Path = RESULTS) -> JSON:
    """Lay out the dataset in `into` and return the score report it contains. Refuses results that do not check:
    test episodes or diagnostics from another lock, an episode without its decision log, a missing environment
    record."""
    report = score(suite, seed_set, results)  # raises on episodes from another lock
    lock = locked_digest(suite)
    if seed_set == "test" and lock is None:
        raise StaleResultsError(f"suite {suite.id} is not frozen; only frozen test results are published")
    for player_dir in _episode_dirs(suite, seed_set, results):
        relative = player_dir.relative_to(results)
        episodes = read_episodes(player_dir)
        for episode in episodes:
            log = decisions_path(player_dir, int(episode["seed"]))
            if not log.exists():
                raise FileNotFoundError(f"{log}: the decision log of an episode is missing")
            _place(log, into / relative / "decisions" / log.name)
        if episodes:
            _place(player_dir / "episodes.jsonl", into / relative / "episodes.jsonl")
    suite_dir = results / suite.id
    for kind in ("latency", "bias"):
        for path in sorted((suite_dir / kind).glob("*.json")):
            if seed_set == "test" and read_json(path).get("lock") != lock:
                raise StaleResultsError(f"{path}: measured under another suite lock; run `arena {kind}` again")
            _place(path, into / suite.id / kind / path.name)
    environment = suite_dir / "environment.json"
    if seed_set == "test" and not environment.exists():
        raise FileNotFoundError(f"{environment} is missing; record it with `arena env`")
    for path in (environment, suite_dir / "laya-cuts.json"):
        if path.exists():
            _place(path, into / suite.id / path.name)
    write_json(into / suite.id / f"scores-{seed_set}.json", report)
    _place(suite.path, into / "suites" / suite.path.name)
    if suite.lock_path.exists():
        _place(suite.lock_path, into / "suites" / suite.lock_path.name)
    (into / "README.md").write_text(card(suite, seed_set, report))
    return report


def _ranking(board: JSON) -> list[str]:
    rows = ["| rank | player | index | 95% interval |", "|---:|---|---:|---|"]
    for player in board["ranking"]:
        info = board["players"][player]
        low, high = info.get("index_ci") or (None, None)
        interval = f"{low:.1f} to {high:.1f}" if low is not None and high is not None else "n/a"
        rows.append(f"| {info['rank']} | {player} | {info['index']:.1f} | {interval} |")
    return rows


def card(suite: Suite, seed_set: str, report: JSON) -> str:
    lock = report.get("lock")
    lines = [
        "---",
        "license: mit",
        "pretty_name: Typed-decision game arena",
        "tags:",
        "- games",
        "- benchmark",
        "- decision-making",
        "- typed-decision",
        "configs:",
        "- config_name: episodes",
        f'  data_files: "{suite.id}/{seed_set}/**/episodes.jsonl"',
        "---",
        "",
        "# Typed-decision game arena",
        "",
        "Typed-decision models (text and a list of allowed answers in, one answer and its probabilities out) play "
        "Tetris, Snake, Connect Four, Pong and Breakout under one fixed protocol. This dataset holds every decision "
        f"of suite **{suite.id}** on the **{seed_set}** seeds; the protocol, the code and the leaderboard are in "
        f"[the arena repository]({GITHUB}).",
        "",
        f"Suite lock: `{lock}`" if lock else "The suite is not frozen: these are development results.",
        "",
    ]
    for board_id, board in report["boards"].items():
        if board["ranking"]:
            lines += [f"## {board_id}", "", *_ranking(board), ""]
    lines += [
        "## Layout",
        "",
        "```",
        f"suites/{suite.id}.toml, suites/{suite.id}.lock.json      the protocol and its lock",
        f"{suite.id}/{seed_set}/<board>/<game>/<player>/episodes.jsonl              one line per episode",
        f"{suite.id}/{seed_set}/<board>/<game>/<player>/decisions/<seed>.jsonl.gz   every decision, then the end",
        f"{suite.id}/latency/<player>.json, {suite.id}/bias/<player>.json     diagnostics",
        f"{suite.id}/environment.json                                   GPU, driver, packages of every runtime",
        f"{suite.id}/scores-{seed_set}.json                                    normalised scores, intervals, tests",
        "```",
        "",
        "Field by field descriptions are in the repository's `results/README.md`. To check a log, check out the "
        f"repository at the version that wrote it and run `uv run arena verify --seed-set {seed_set} --results "
        "<this dataset>`: every episode is replayed from its seed and its logged choices and must match byte for "
        "byte.",
        "",
    ]
    return "\n".join(lines)


def _hub() -> Hub:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("publishing needs huggingface-hub: uv sync --extra publish") from None
    hub: Hub = HfApi()
    return hub


def publish(
    suite: Suite,
    seed_set: str,
    repo_id: str,
    *,
    results: Path = RESULTS,
    private: bool = True,
    api: Hub | None = None,
) -> JSON:
    """Stage and upload in one commit. Returns the score report that went up."""
    hub = api or _hub()
    # staged next to the results, so that the logs are hard links rather than copies
    with tempfile.TemporaryDirectory(prefix=".dataset-", dir=results if results.exists() else ROOT) as tmp:
        staging = Path(tmp)
        report = stage(suite, seed_set, staging, results)
        hub.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
        lock = report.get("lock")
        hub.upload_folder(
            repo_id=repo_id,
            folder_path=staging,
            repo_type="dataset",
            commit_message=f"{suite.id} {seed_set} results" + (f" (lock {lock[:12]})" if lock else ""),
            delete_patterns=[f"{suite.id}/{seed_set}/**"],
        )
    return report
