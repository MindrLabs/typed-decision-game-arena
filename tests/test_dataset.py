"""Publishing results as a dataset: layout, one commit, refusals, and that the published logs verify."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from arena.dataset import publish, stage
from arena.logs import decisions_path, run_dir
from arena.replay import verify
from arena.runner import run
from arena.suite import Suite


def quiet(line: str) -> None:
    pass


class FakeHub:
    """Records the calls and keeps a copy of what was uploaded (the staging directory is gone afterwards)."""

    def __init__(self, into: Path) -> None:
        self.into = into
        self.calls: list[tuple[object, ...]] = []

    def create_repo(self, repo_id: str, *, repo_type: str, private: bool, exist_ok: bool) -> None:
        self.calls.append(("create", repo_id, repo_type, private, exist_ok))

    def upload_folder(
        self,
        *,
        repo_id: str,
        folder_path: str | Path,
        repo_type: str,
        commit_message: str,
        delete_patterns: list[str],
    ) -> None:
        shutil.copytree(folder_path, self.into)
        self.calls.append(("upload", repo_id, repo_type, commit_message, delete_patterns))


def test_results_go_up_in_one_commit_and_verify_from_there(suite: Suite, results: Path, tmp_path: Path) -> None:
    for player in ("random", "reference"):
        run(suite, "macro", "snake", player, [1001], seed_set="dev", results=results, progress=quiet)
    hub = FakeHub(tmp_path / "uploaded")
    publish(suite, "dev", "someone/arena", results=results, api=hub)
    assert hub.calls == [
        ("create", "someone/arena", "dataset", True, True),
        ("upload", "someone/arena", "dataset", "v0.1 dev results", ["v0.1/dev/**"]),
    ]
    up = hub.into
    assert (up / "v0.1/dev/macro/snake/reference/episodes.jsonl").exists()
    assert (up / "v0.1/dev/macro/snake/reference/decisions/1001.jsonl.gz").exists()
    assert (up / "suites/v0.1.toml").exists()
    assert (up / "v0.1/scores-dev.json").exists()
    card = (up / "README.md").read_text()
    assert card.startswith("---\nlicense: mit\n")
    assert "The suite is not frozen" in card
    assert not list(results.glob(".dataset-*"))  # the staging directory is removed
    assert [v.problem for v in verify(suite, "dev", results=up)] == [None, None]  # as the card promises


def test_an_episode_without_its_decision_log_is_not_published(suite: Suite, results: Path, tmp_path: Path) -> None:
    run(suite, "macro", "snake", "random", [1001], seed_set="dev", results=results, progress=quiet)
    decisions_path(run_dir(suite.id, "dev", "macro", "snake", "random", results=results), 1001).unlink()
    hub = FakeHub(tmp_path / "uploaded")
    with pytest.raises(FileNotFoundError, match="decision log"):
        publish(suite, "dev", "someone/arena", results=results, api=hub)
    assert hub.calls == []


def test_test_results_need_an_environment_record(frozen: Suite, results: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="arena env"):
        stage(frozen, "test", tmp_path / "staging", results)
