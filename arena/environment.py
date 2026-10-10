"""The software and hardware a run used, written next to the results (`arena env`).

Model outputs can move with the runtime (a different kernel build can flip near-ties), so every published set of
results carries the exact package list of each model runtime, the model-compose revision, the GPU and driver, and
this repository's commit.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from arena import __version__
from arena.core import JSON
from arena.suite import ROOT


def _run(command: list[str], cwd: Path = ROOT) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def runtime_packages(runtimes: Path = ROOT / ".runtime") -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    if not runtimes.exists():
        return found
    for runtime in sorted(p for p in runtimes.iterdir() if (p / "bin" / "python").exists()):
        frozen = _run(["uv", "pip", "freeze", "--python", str(runtime / "bin" / "python")])
        if frozen is not None:
            found[runtime.name] = frozen.splitlines()
    return found


OUTPUTS = ("results", "webui/data")  # what runs write; not part of the code that produced them


def dirty(root: Path = ROOT) -> bool | None:
    """The checkout differs from its commit outside the outputs (tracked or untracked). None outside git."""
    excluded = [f":(top,exclude){path}" for path in OUTPUTS]
    status = _run(["git", "status", "--porcelain", "--", ":(top)", *excluded], cwd=root)
    return None if status is None else bool(status)


def describe() -> JSON:
    gpu = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    return {
        "recorded": datetime.now(UTC).isoformat(timespec="seconds"),
        "arena": __version__,
        "repository_commit": _run(["git", "rev-parse", "HEAD"]),
        "repository_dirty": dirty(),
        "model_compose": (ROOT / "scripts" / "model-compose.rev").read_text().strip(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": platform.platform(),
        "gpu": gpu.splitlines() if gpu else [],
        "runtimes": runtime_packages(),
    }
