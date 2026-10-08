"""Contestants, read from model-compose.yml: every workflow there is one player, named by its workflow id.

The YAML is the single source of truth for which checkpoint (and revision) a player is; the arena reads it
instead of keeping a second list.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from arena.families import FAMILIES
from arena.suite import ROOT

COMPOSE_FILE = ROOT / "model-compose.yml"
BASELINES = ("random", "reference")


@dataclass(frozen=True)
class Contestant:
    id: str
    title: str
    description: str
    family: str
    repository: str | None
    revision: str | None
    base_model: str | None = None
    preset: str | None = None
    #: sha256 of the component's settings (after YAML anchors expand): serving settings such as Laya's token
    #: budgets change answers, so every result records which settings produced it.
    config_sha: str = ""


def _model_ref(model: Any) -> tuple[str | None, str | None]:
    if isinstance(model, str):
        return model, None
    if isinstance(model, dict):
        return model.get("repository") or model.get("path"), model.get("revision")
    return None, None


def contestants(path: Path = COMPOSE_FILE) -> dict[str, Contestant]:
    data = yaml.safe_load(path.read_text())
    components = {component["id"]: component for component in data.get("components", [])}
    found: dict[str, Contestant] = {}
    for workflow in data.get("workflows", []):
        component = components[workflow["job"]["component"]]
        if component.get("task") != "typed-decision":
            continue
        family = component["family"]
        if family not in FAMILIES:
            raise ValueError(f"{workflow['id']}: family {family!r} has no adapter in arena/families.py")
        repository, revision = _model_ref(component.get("model"))
        if repository is None and family == "laya":
            repository = "convaiinnovations/laya"
        base, _ = _model_ref(component.get("base_model"))
        found[workflow["id"]] = Contestant(
            workflow["id"],
            workflow.get("title", workflow["id"]),
            workflow.get("description", ""),
            family,
            repository,
            revision,
            base,
            component.get("preset"),
            hashlib.sha256(json.dumps(component, sort_keys=True).encode()).hexdigest(),
        )
    clash = set(found) & set(BASELINES)
    if clash:
        raise ValueError(f"workflow ids {sorted(clash)} are reserved for baselines")
    return found
