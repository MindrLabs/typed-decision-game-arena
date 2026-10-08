"""The GPU as nvidia-smi reports it: recorded next to every latency measurement, and watched by the campaign so
that latency is measured only while nothing else computes on the GPU.

What disturbs a measurement is computation, not memory: an idle runtime keeps its CUDA context (about 400 MiB on
the GB10, over 1 GiB for some) and a loaded model that gets no requests costs nothing. While the campaign waits
it sends no requests, so the device's utilisation is then exactly the other work on the GPU. Per-process
utilisation is not reported on the GB10; where the device's is not either, a process with more than an idle
context's memory counts as busy instead. Names are reduced to what is worth publishing: an arena model runtime
shows as its player id (`.runtime/<id>/bin/python`), anything else as its executable name, never as a local path.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import PurePath

RUNTIME_MARKER = "/.runtime/"
# A loaded model holds far more (the smallest player, Laya, about 2.8 GiB); an idle CUDA context far less.
BUSY_MIB = 1024


@dataclass(frozen=True, slots=True)
class GpuProcess:
    pid: int
    path: str
    memory_mib: int | None

    @property
    def runtime(self) -> str | None:
        """The arena player this process serves, when it is one of the arena's model runtimes."""
        if RUNTIME_MARKER not in self.path:
            return None
        return self.path.split(RUNTIME_MARKER, 1)[1].split("/", 1)[0] or None

    @property
    def busy(self) -> bool:
        """Holding more than an idle context. Unknown memory counts as busy."""
        return self.memory_mib is None or self.memory_mib > BUSY_MIB

    @property
    def label(self) -> str:
        name = f"runtime {self.runtime}" if self.runtime else PurePath(self.path).name
        return name if self.memory_mib is None else f"{name} ({self.memory_mib} MiB)"


def _smi(query: str) -> list[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    result = subprocess.run(
        ["nvidia-smi", query, "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()] if result.returncode == 0 else []


def parse_process(line: str) -> GpuProcess:
    """One `pid, process_name, used_memory` line (the name may itself contain commas)."""
    pid, rest = line.split(",", 1)
    path, memory = rest.rsplit(",", 1)
    memory = memory.strip()
    return GpuProcess(int(pid), path.strip(), int(memory) if memory.isdigit() else None)


def gpu_processes() -> list[GpuProcess]:
    return [parse_process(line) for line in _smi("--query-compute-apps=pid,process_name,used_memory")]


def gpu_utilization() -> int | None:
    """The device's utilisation in percent over the last sample period, or None where it is not reported."""
    values = _smi("--query-gpu=utilization.gpu")
    return int(values[0]) if values and values[0].isdigit() else None


def gpu_name() -> str | None:
    names = _smi("--query-gpu=name")
    return names[0] if names else None
