"""Site data: webui/data/index.json (scores, players, diagnostics) and a few gzipped replays per player.

The site (site/, built into webui/) only reads these files, so the leaderboard works from any static host and
from model-compose's static web UI alike. Replays are gzipped JSON the browser inflates with DecompressionStream.
"""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from arena import __version__
from arena.bias import bias_path
from arena.core import JSON
from arena.logs import RESULTS, decisions_path, read_decisions, read_episodes, read_final, read_json, run_dir
from arena.registry import contestants
from arena.runner import latency_path
from arena.score import score
from arena.suite import ROOT, Suite, locked_digest

SCHEMA = 1
WEBUI_DATA = ROOT / "webui" / "data"

GAMES: dict[str, JSON] = {
    "tetris": {"title": "Tetris", "score": "lines cleared"},
    "snake": {"title": "Snake", "score": "food eaten"},
    "connect4": {"title": "Connect Four", "score": "points per game (win 1, draw 0.5)"},
    "pong": {"title": "Pong", "score": "points won minus points lost"},
    "breakout": {"title": "Breakout", "score": "points"},
}

BASELINE_INFO: dict[str, JSON] = {
    "random": {
        "title": "Random",
        "kind": "baseline",
        "description": "A uniformly random legal option. Defines 0 on every normalised score.",
    },
    "reference": {
        "title": "Reference",
        "kind": "baseline",
        "description": "A strong rule-based player per game that reads the game state directly, never the text. "
        "Defines 100 on every normalised score.",
    },
}


def _players() -> dict[str, JSON]:
    players = dict(BASELINE_INFO)
    for c in contestants().values():
        players[c.id] = {
            "title": c.title,
            "kind": "model",
            "description": c.description,
            "family": c.family,
            "repository": c.repository,
            "revision": c.revision,
            "base_model": c.base_model,
            "preset": c.preset,
        }
    return players


def _write_replay(suite: Suite, seed_set: str, episode: JSON, out: Path, results: Path) -> str:
    board, game, player, seed = episode["board"], episode["game"], episode["player"], int(episode["seed"])
    source = decisions_path(run_dir(suite.id, seed_set, board, game, player, results=results), seed)
    relative = f"replays/{board}/{game}/{player}/{seed}.json.gz"
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": SCHEMA,
        "board": board,
        "game": game,
        "player": player,
        "seed": seed,
        "score": episode["score"],
        "metrics": episode.get("metrics", {}),
        "delay_steps": episode.get("delay_steps", 0),
        "decisions": list(read_decisions(source)),
        "final": read_final(source),
    }
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    # mtime=0 keeps the archive byte-identical across exports
    target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    return relative


def export(
    suite: Suite,
    seed_set: str,
    *,
    out: Path = WEBUI_DATA,
    results: Path = RESULTS,
    replays_per_player: int = 2,
) -> Path:
    report = score(suite, seed_set, results)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    players = _players()
    replays: list[JSON] = []
    for board, game in suite.pairs():
        game_dir = results / suite.id / seed_set / board / game
        if not game_dir.exists():
            continue
        for player_dir in sorted(p for p in game_dir.iterdir() if p.is_dir()):
            for episode in read_episodes(player_dir)[:replays_per_player]:
                path = _write_replay(suite, seed_set, episode, out, results)
                replays.append(
                    {
                        "board": board,
                        "game": game,
                        "player": player_dir.name,
                        "seed": episode["seed"],
                        "score": episode["score"],
                        "decisions": episode["decisions"],
                        "path": path,
                    }
                )
    diagnostics: dict[str, dict[str, JSON]] = {"latency": {}, "bias": {}}
    for player_id in players:
        latency = latency_path(suite.id, player_id, results)
        bias = bias_path(suite.id, player_id, results)
        if latency.exists():
            diagnostics["latency"][player_id] = read_json(latency)
        if bias.exists():
            diagnostics["bias"][player_id] = read_json(bias)
    boards = sorted(suite.boards.values(), key=lambda b: b.order)
    index = {
        "schema": SCHEMA,
        "arena": __version__,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "suite": {
            "id": suite.id,
            "frozen": locked_digest(suite) is not None,
            "lock": locked_digest(suite),
            "group_size": suite.group_size,
            "bootstrap": suite.bootstrap,
            "confidence": suite.confidence,
            "sticky": suite.sticky,
        },
        "seed_set": seed_set,
        "boards": [
            {
                "id": b.id,
                "title": b.title,
                "summary": b.summary,
                "games": list(b.games),
                "anchor_board": b.based_on or b.id,
                "seeds": {g: len(spec.seeds[seed_set]) for g, spec in b.games.items()},
            }
            for b in boards
        ],
        "games": GAMES,
        "players": players,
        "scores": report["boards"],
        "latency": diagnostics["latency"],
        "bias": diagnostics["bias"],
        "replays": replays,
    }
    (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return out / "index.json"
