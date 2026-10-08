from __future__ import annotations

import re
from pathlib import Path

import pytest

from arena.families import FAMILIES
from arena.registry import contestants


def test_every_workflow_is_a_contestant() -> None:
    players = contestants()
    assert set(players) == {
        "clef",
        "clef-flash",
        "kev-9b",
        "kev-4b",
        "kev-0.8b",
        "nimble-v2",
        "nimble",
        "laya-english",
        "laya-typed",
        "laya-multilingual",
    }
    for c in players.values():
        assert c.family in FAMILIES
        assert re.fullmatch(r"[0-9a-f]{64}", c.config_sha)
        if c.family != "laya":  # Laya's driver takes the bundle repository only
            assert c.revision is not None and re.fullmatch(r"[0-9a-f]{40}", c.revision), c.id


def test_baseline_ids_are_reserved(tmp_path: Path) -> None:
    compose = tmp_path / "model-compose.yml"
    compose.write_text(
        """
workflows:
  - id: random
    job: { component: m }
components:
  - id: m
    type: model
    task: typed-decision
    family: kev
    model: jaredpalmer/kev-0.8b
"""
    )
    with pytest.raises(ValueError, match="reserved"):
        contestants(compose)
