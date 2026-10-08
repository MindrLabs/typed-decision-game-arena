"""Prepare every model runtime once, one component at a time (no model weights are downloaded).

`model-compose up` starts all components together. On a first start, components of one family install the same
GitHub package out of one shared clone directory at the same time, and the installs can trip over each other.
Starting each component alone once installs everything; afterwards `scripts/serve.sh` finds the packages in
place and starts in seconds.

    uv run python scripts/setup_runtimes.py              every component in model-compose.yml
    uv run python scripts/setup_runtimes.py kev-0.8b     only some

It also adds what a driver needs but does not install yet. Clef loads a Qwen3-VL processor, which refuses to
start without torchvision even for text, and the pinned Clef driver does not install it
(hanyeol/model-compose#39): the script adds the torchvision release paired with the runtime's torch, from the
same wheel index, without touching anything else.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REV = (ROOT / "scripts" / "model-compose.rev").read_text().strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/workflows", timeout=2) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


def stop(process: subprocess.Popen[bytes]) -> None:
    for sig, wait in ((signal.SIGINT, 60), (signal.SIGTERM, 20), (signal.SIGKILL, 5)):
        if process.poll() is not None:
            return
        os.killpg(process.pid, sig)
        try:
            process.wait(wait)
        except subprocess.TimeoutExpired:
            continue


def add_torchvision(python: Path) -> None:
    """torchvision 0.(m+15).p pairs with torch 2.m.p; the local version (+cu130) names the wheel index."""
    torch = subprocess.run(
        [str(python), "-c", "import torch; print(torch.__version__)"], capture_output=True, text=True, check=True
    ).stdout.strip()
    release, _, channel = torch.partition("+")
    _, minor, patch = [*release.split("."), "0"][:3]
    vision = f"0.{int(minor) + 15}.{patch}"
    index = f"https://download.pytorch.org/whl/{channel or 'cpu'}"
    subprocess.run(
        ["uv", "pip", "install", "--no-deps", "--python", str(python), f"torchvision=={vision}", "--index-url", index],
        check=True,
    )


# Families whose driver needs torchvision without installing it (Clef's Qwen3-VL processor).
NEEDS_TORCHVISION = {"clef"}


def setup(component: dict[str, object], workflow: dict[str, object], timeout: float) -> bool:
    component = dict(component)
    runtime = dict(component["runtime"])  # type: ignore[call-overload]
    runtime["path"] = str(ROOT / str(runtime["path"]))
    component["runtime"] = runtime
    port = free_port()
    config = {
        "controller": {"adapter": {"type": "http-server", "host": "127.0.0.1", "port": port, "base_path": "/api"}},
        "workflows": [workflow],
        "components": [component],
    }
    logs = ROOT / ".runtime" / "setup-logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{component['id']}.log"
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
        compose = handle.name
    command = [
        "uvx",
        "--python",
        "3.12",
        "--from",
        f"git+https://github.com/hanyeol/model-compose@{REV}",
        "model-compose",
        "-f",
        compose,
        "up",
    ]
    started = time.monotonic()
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic() - started < timeout:
                if ready(port):
                    return True
                if process.poll() is not None:
                    return False
                time.sleep(2)
            return False
        finally:
            stop(process)
            Path(compose).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("components", nargs="*", help="component ids (default: all)")
    parser.add_argument("--timeout", type=float, default=3600, help="seconds per component")
    args = parser.parse_args()
    data = yaml.safe_load((ROOT / "model-compose.yml").read_text())
    workflows = {w["job"]["component"]: w for w in data["workflows"]}
    failed = []
    for component in data["components"]:
        if args.components and component["id"] not in args.components:
            continue
        clock = time.monotonic()
        ok = setup(component, workflows[component["id"]], args.timeout)
        if ok and component.get("family") in NEEDS_TORCHVISION:
            add_torchvision(ROOT / str(component["runtime"]["path"]) / "bin" / "python")
        took = time.monotonic() - clock
        status = "ok  " if ok else "FAIL"
        print(f"{status} {component['id']} ({took:.0f}s, log .runtime/setup-logs/{component['id']}.log)", flush=True)
        if not ok:
            failed.append(component["id"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
