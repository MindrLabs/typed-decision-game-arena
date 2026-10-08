"""nvidia-smi lines into processes: which are arena runtimes, which are busy, and what gets published."""

from __future__ import annotations

from arena.gpu import parse_process


def test_an_arena_runtime_shows_as_its_player() -> None:
    process = parse_process("3602889, /home/someone/arena/.runtime/laya-typed/bin/python, 2843")
    assert process.runtime == "laya-typed"
    assert process.busy
    assert process.label == "runtime laya-typed (2843 MiB)"  # no local path in published files


def test_an_unloaded_runtime_keeps_only_an_idle_context() -> None:
    process = parse_process("3602907, /home/someone/arena/.runtime/laya-english/bin/python, 399")
    assert not process.busy


def test_other_processes_and_unknown_memory() -> None:
    process = parse_process("7, /opt/tools/sd, with, commas, [N/A]")
    assert process.path == "/opt/tools/sd, with, commas"
    assert process.runtime is None
    assert process.memory_mib is None and process.busy  # unknown memory counts as busy
    assert process.label == "sd, with, commas"
