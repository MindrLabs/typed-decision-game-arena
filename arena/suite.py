"""Suite definitions (suites/<id>.toml) and the lock that freezes them.

The lock records the sha256 of the suite file and of every source file that shapes what a player sees or how a
score comes about, plus the versions of the libraries that run the games. Test-seed runs refuse to start unless
the working tree matches the lock, so a published result always corresponds to one frozen protocol.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SUITES = ROOT / "suites"

# Files whose content decides what players see and how scores come about. Runner I/O, scoring and the site
# are not here: they can change without changing a single decision.
LOCKED_SOURCES = (
    "arena/core.py",
    "arena/seeding.py",
    "arena/protocol.py",
    "arena/families.py",
    "arena/episode.py",
    "arena/tasks.py",
    "arena/games/__init__.py",
    "arena/games/atari.py",
    "arena/games/tetris.py",
    "arena/games/snake.py",
    "arena/games/connect4.py",
    "arena/games/pong.py",
    "arena/games/breakout.py",
)
# A suite of kind "duel" (models playing each other) also locks the module that runs those games.
DUEL_SOURCES = ("arena/duel.py",)
LOCKED_PACKAGES = ("ale-py", "gymnasium", "numpy")

SEED_SETS = ("dev", "test")


def parse_seeds(spec: str) -> list[int]:
    """'1-5,8,10-12' -> [1, 2, 3, 4, 5, 8, 10, 11, 12]."""
    seeds: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            low, high = (int(x) for x in part.split("-", 1))
            if high < low:
                raise ValueError(f"empty seed range {part!r}")
            seeds.extend(range(low, high + 1))
        else:
            seeds.append(int(part))
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"seed list {spec!r} repeats a seed")
    return seeds


@dataclass(frozen=True)
class GameSpec:
    board: str
    game: str
    track: str
    params: dict[str, Any]
    reference: dict[str, Any]
    seeds: dict[str, list[int]]


@dataclass(frozen=True)
class BoardSpec:
    id: str
    title: str
    summary: str
    order: int
    games: dict[str, GameSpec]
    based_on: str | None = None
    step_ms: float | None = None

    @property
    def track(self) -> str:
        return "macro" if self.id == "macro" else "frame"


@dataclass(frozen=True)
class Suite:
    id: str
    path: Path
    group_size: int
    bootstrap: int
    confidence: float
    sticky: float
    boards: dict[str, BoardSpec] = field(default_factory=dict)
    #: "single" (each player alone against the game) or "duel" (models against each other)
    kind: str = "single"

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(".lock.json")

    def board(self, board: str) -> BoardSpec:
        try:
            return self.boards[board]
        except KeyError:
            raise KeyError(f"suite {self.id} has no board {board!r}; boards: {sorted(self.boards)}") from None

    def game(self, board: str, game: str) -> GameSpec:
        spec = self.board(board)
        try:
            return spec.games[game]
        except KeyError:
            raise KeyError(f"board {board!r} has no game {game!r}; games: {sorted(spec.games)}") from None

    def pairs(self) -> list[tuple[str, str]]:
        """(board, game) in display order."""
        boards = sorted(self.boards.values(), key=lambda b: b.order)
        return [(b.id, g) for b in boards for g in b.games]


def _game_spec(board: str, track: str, game: str, raw: dict[str, Any]) -> GameSpec:
    raw = dict(raw)
    seeds_raw = raw.pop("seeds", None)
    if not isinstance(seeds_raw, dict) or set(seeds_raw) != set(SEED_SETS):
        raise ValueError(f"{board}/{game}: seeds must define exactly {SEED_SETS}")
    seeds = {name: parse_seeds(str(value)) for name, value in seeds_raw.items()}
    if set(seeds["dev"]) & set(seeds["test"]):
        raise ValueError(f"{board}/{game}: dev and test seeds overlap")
    reference = dict(raw.pop("reference", {}))
    return GameSpec(board=board, game=game, track=track, params=raw, reference=reference, seeds=seeds)


def load_suite(suite_id: str = "v0.1", directory: Path = SUITES) -> Suite:
    path = directory / f"{suite_id}.toml"
    data = tomllib.loads(path.read_text())
    if data.get("id") != suite_id:
        raise ValueError(f"{path} declares id {data.get('id')!r}, expected {suite_id!r}")
    boards: dict[str, BoardSpec] = {}
    raw_boards: dict[str, Any] = data["boards"]
    for board_id, raw in raw_boards.items():
        if "from" in raw:
            continue
        track = "macro" if board_id == "macro" else "frame"
        games = {g: _game_spec(board_id, track, g, spec) for g, spec in raw["games"].items()}
        boards[board_id] = BoardSpec(board_id, raw["title"], raw["summary"], int(raw["order"]), games)
    for board_id, raw in raw_boards.items():
        if "from" not in raw:
            continue
        base = boards[raw["from"]]
        games = {
            g: GameSpec(board=board_id, game=g, track=s.track, params=s.params, reference=s.reference, seeds=s.seeds)
            for g, s in base.games.items()
        }
        boards[board_id] = BoardSpec(
            board_id, raw["title"], raw["summary"], int(raw["order"]), games, raw["from"], float(raw["step_ms"])
        )
    return Suite(
        suite_id,
        path,
        int(data["group_size"]),
        int(data["bootstrap"]),
        float(data["confidence"]),
        float(data["atari"]["sticky"]),
        boards,
        _kind(data),
    )


def _kind(data: dict[str, Any]) -> str:
    kind = str(data.get("kind", "single"))
    if kind not in ("single", "duel"):
        raise ValueError(f"suite kind must be 'single' or 'duel', got {kind!r}")
    return kind


def locked_sources(suite: Suite) -> tuple[str, ...]:
    return LOCKED_SOURCES + (DUEL_SOURCES if suite.kind == "duel" else ())


# --- lock -----------------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(suite: Suite, root: Path = ROOT) -> dict[str, Any]:
    return {
        "suite": suite.id,
        "suite_file": {str(suite.path.relative_to(root)): _sha256(suite.path)},
        "sources": {name: _sha256(root / name) for name in locked_sources(suite)},
        "packages": {name: importlib.metadata.version(name) for name in LOCKED_PACKAGES},
        "python": ".".join(platform.python_version_tuple()[:2]),
    }


def manifest_digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def freeze(suite: Suite, root: Path = ROOT) -> Path:
    if suite.lock_path.exists():
        raise FileExistsError(f"{suite.lock_path} exists; a frozen suite is never re-frozen (start a new version)")
    data = manifest(suite, root)
    suite.lock_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return suite.lock_path


def lock_differences(suite: Suite, root: Path = ROOT) -> list[str]:
    """Empty when the working tree matches the lock; otherwise one line per difference."""
    if not suite.lock_path.exists():
        return [f"{suite.lock_path.name} does not exist (the suite is not frozen yet)"]
    locked = json.loads(suite.lock_path.read_text())
    current = manifest(suite, root)
    problems = [
        f"{section}: {name} {locked[section].get(name)} -> {current[section].get(name)}"
        for section in ("suite_file", "sources", "packages")
        for name in sorted(set(locked[section]) | set(current[section]))
        if locked[section].get(name) != current[section].get(name)
    ]
    if locked["python"] != current["python"]:
        problems.append(f"python: {locked['python']} -> {current['python']}")
    return problems


def locked_digest(suite: Suite) -> str | None:
    if not suite.lock_path.exists():
        return None
    return manifest_digest(json.loads(suite.lock_path.read_text()))
