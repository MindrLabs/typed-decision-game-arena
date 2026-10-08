"""How much of each question Laya actually reads (needs the `diag` extra: tokenizers, huggingface-hub).

Laya splits its token budget into a head (instructions and options, `max_head_length`) and the state (the rest
of `max_seq_length`); a longer state is cut, and each option description is capped at 48 tokens. This counts
tokens with the encoder's own tokenizer on the probe questions of every game and reports how often each cut
applies. Counts include no special tokens or option markers, so they slightly understate Laya's real usage.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml

from arena.core import JSON
from arena.probe import sample_questions
from arena.registry import COMPOSE_FILE
from arena.suite import Suite

TOKENIZERS = {
    "english": "answerdotai/ModernBERT-large",
    "typed-decisions": "answerdotai/ModernBERT-large",
    "multilingual": "jhu-clsp/mmBERT-base",
}
OPTION_CAP = 48


def _laya_budgets() -> dict[str, JSON]:
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    components = {c["id"]: c for c in data["components"]}
    budgets = {}
    for workflow in data["workflows"]:
        component = components[workflow["job"]["component"]]
        if component.get("family") == "laya":
            budgets[workflow["id"]] = {
                "preset": component.get("preset", "multilingual"),
                "max_seq_length": int(component["max_seq_length"]),
                "max_head_length": int(component["max_head_length"]),
            }
    return budgets


def _tokenizer(name: str) -> Any:
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    return Tokenizer.from_file(hf_hub_download(name, "tokenizer.json"))


def measure(suite: Suite, *, sample: int = 100, progress: Callable[[str], None] = print) -> JSON:
    report: JSON = {}
    budgets = _laya_budgets()
    cache: dict[str, Any] = {}
    questions = {
        f"{board}/{game}": sample_questions(suite, board, game, sample)
        for board, game in suite.pairs()
        if suite.board(board).step_ms is None
    }
    for player, budget in budgets.items():
        name = TOKENIZERS[budget["preset"]]
        tokenizer = cache.setdefault(name, _tokenizer(name))

        def count(text: str, tokenizer: Any = tokenizer) -> int:
            return len(tokenizer.encode(text, add_special_tokens=False).ids)

        games: JSON = {}
        for key, items in questions.items():
            head_over = state_cut = option_cut = 0
            longest_state = 0
            for q in items:
                head = count(q.instructions) + sum(min(count(o.text), OPTION_CAP) for o in q.options)
                state = count(q.state)
                longest_state = max(longest_state, state)
                head_over += head > budget["max_head_length"]
                state_cut += state > budget["max_seq_length"] - min(head, budget["max_head_length"])
                option_cut += any(count(o.text) > OPTION_CAP for o in q.options)
            n = len(items)
            games[key] = {
                "n": n,
                "head_over_budget": round(head_over / n, 4) if n else None,
                "state_cut": round(state_cut / n, 4) if n else None,
                "option_cut": round(option_cut / n, 4) if n else None,
                "longest_state_tokens": longest_state,
            }
        report[player] = {"budget": budget, "tokenizer": name, "games": games}
        progress(f"{player}: {games}")
    return report
