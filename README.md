[English](README.md) · [한국어](README.ko.md) · [中文](README.zh-cn.md)

# typed-decision-game-arena

This repository has typed-decision models play Tetris, Snake, Connect Four, Pong and Breakout, one decision at a
time, under a single frozen protocol, and ranks them on a leaderboard with replays of every published game.

Every model is served with [model-compose](https://github.com/hanyeol/model-compose) and reads byte-identical
text. Scores are scaled between a random player (0) and a strong rule-based reference player (100) on the same
seeds, so adding a model never moves anyone else's score. The leaderboard and the replay viewer are a static site
that model-compose serves next to the models.

**Status:** suite v0.1 is frozen (lock `17f3ed7e0f66…`). The test results of ten models are in
[`results/v0.1`](results/v0.1) and on the leaderboard, and every decision is in the Hugging Face dataset
`MindrLabs/typed-decision-game-arena`.

## Contents

- [Players](#players)
- [Quick Start](#quick-start)
- [Boards and games](#boards-and-games)
- [How the comparison is kept fair](#how-the-comparison-is-kept-fair)
- [Scores](#scores)
- [Versus](#versus)
- [Full runs](#full-runs)
- [Adding a model](#adding-a-model)
- [Repository layout](#repository-layout)
- [License](#license)

## Players

A typed-decision model takes a text and a list of allowed answers and returns one of them, with a probability for
each. It never writes free text, so it cannot answer outside the list.

| Player | Model | Size | Family |
|---|---|---|---|
| `clef` | [`Cloudflare/clef`](https://huggingface.co/Cloudflare/clef), routing head and LoRA on Qwen3.8-27B | 27B | clef |
| `clef-flash` | [`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash), on Qwen3.5-9B | 9B | clef |
| `kev-9b` | [`jaredpalmer/kev-9b`](https://huggingface.co/jaredpalmer/kev-9b), LoRA and pointer head on Qwen3.5-9B-Base | 9B | kev |
| `kev-4b` | [`jaredpalmer/kev-4b`](https://huggingface.co/jaredpalmer/kev-4b), on Qwen3.5-4B-Base | 4B | kev |
| `kev-0.8b` | [`jaredpalmer/kev-0.8b`](https://huggingface.co/jaredpalmer/kev-0.8b), on Qwen3.5-0.8B-Base | 0.8B | kev |
| `nimble-v2` | [`bespokelabs/Bespoke-Nimble-9B-v2`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B-v2), LoRA on Qwen3.5-9B | 9B | nimble |
| `nimble` | [`bespokelabs/Bespoke-Nimble-9B`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B), first release | 9B | nimble |
| `laya-english` | [`convaiinnovations/laya`](https://huggingface.co/convaiinnovations/laya), english checkpoint (ModernBERT-large) | 421M | laya |
| `laya-typed` | the same bundle, typed-decisions checkpoint | 421M | laya |
| `laya-multilingual` | the same bundle, multilingual checkpoint (mmBERT-base) | 322M | laya |
| `random` | a uniformly random legal option: 0 on every scale | | anchor |
| `reference` | a strong rule-based player per game, reading the game state directly: 100 on every scale | | anchor |

Checkpoints and revisions are pinned in [`model-compose.yml`](model-compose.yml), the single list of players.

## Quick Start

It needs Linux with an NVIDIA GPU, [uv](https://docs.astral.sh/uv/) and git. We run it on an NVIDIA DGX Spark
(GB10, aarch64). model-compose is fetched by `uvx` at the revision pinned in `scripts/model-compose.rev`.

```bash
git clone https://github.com/MindrLabs/typed-decision-game-arena
cd typed-decision-game-arena
uv sync                                    # the runner
uv run python scripts/setup_runtimes.py    # once: one runtime per model under .runtime/ (no weights yet)
scripts/serve.sh                           # models at http://127.0.0.1:8380/api, leaderboard at :8381
```

In a second terminal, check a model and have it play a development seed:

```bash
uv run arena smoke --player kev-0.8b       # one request per game
uv run arena run --board macro --game snake --player kev-0.8b --seeds dev
uv run arena score --seed-set dev
uv run arena export --seed-set dev         # refresh the leaderboard data, then open http://127.0.0.1:8381
```

`uv run arena show --board macro --game tetris` prints a question exactly as the models receive it.

| On the first run | What happens |
| :---: | --- |
| Runtimes | `setup_runtimes.py` starts each model-compose component alone once, which installs its packages into `.runtime/<player>/` (uv hard-links shared wheels). Starting them all at once on a first start can fail, see [operations](docs/operations.md#once-per-machine) |
| Checkpoints | Each model downloads on its first request: Kev 0.8B 1.8 GB, Kev 4B 9.5 GB, Kev 9B 19.5 GB (base models included), Clef 55 GB, Clef-flash 19.1 GB, the Laya bundle 2.3 GB (all three checkpoints). Nimble downloads its adapter (0.19 GB) and Qwen3.5-9B (19.3 GB) and merges them once into `~/.cache/models/nimble-merged` (18.8 GB) |
| Memory | Models unload after 120 idle seconds, so all players can be declared while only the one being run is in memory |

Example request:

```bash
curl -s 127.0.0.1:8380/api/workflows/runs -H 'Content-Type: application/json' -d '{
  "workflow_id": "kev-0.8b",
  "input": {
    "text": "Snake on a 10 x 10 grid. Head at row 5, column 5, heading up. Food at row 2, column 5.",
    "schema": {"move": {"type": "choice", "instructions": "Choose the move for this step.",
      "criteria": {"left": "turn left: the cell is empty", "straight": "go straight: the cell is empty",
                   "right": "turn right: the cell is empty"}}}
  }
}'
```

It returns `{"status": "completed", "output": {"decision": {"move": "straight"}, "fields": {"move": {"scores": {...}}}}}`.
The Nimble players take the same question as `{"type": "enum", "choices": [...], "description": ..., "choice_descriptions": {...}}`.

## Boards and games

| Board | Timing | One decision is | Games |
|---|---|---|---|
| Macro | turn-based | one meaningful choice: where a piece lands, which band the paddle covers, which way to turn, which column to play | Tetris, Snake, Connect Four, Pong, Breakout |
| Frame | turn-based | one step of the game: a key, or a push of the paddle | Tetris, Pong, Breakout |
| Real-time | the game keeps running while the model thinks | as on the frame board, applied after the model's measured reaction time | Tetris, Pong, Breakout |

Tetris, Snake and Connect Four are implemented in this repository; Pong and Breakout run on the Arcade Learning
Environment with sticky actions (Machado et al. 2018). Per-game rules, options and caps are in
[docs/suite-v0.1.md](docs/suite-v0.1.md).

## How the comparison is kept fair

- **Identical text.** Every model reads the same state, instructions and option sentences; only the JSON around
  them follows each family's question format. No model gets its own prompt.
- **Facts, not advice.** The text describes the position and, for each option, what holds right after it (lines
  cleared, a wall ahead, an immediate four). Nothing ranks, recommends or predicts.
- **No order to lean on.** Options appear in a seeded shuffle; above 8 options a knockout splits them into groups
  and a final. Every model gets the same procedure, and `arena bias` reports how much each follows position.
- **Same seeds for everyone,** with dev seeds for development and test seeds that only run against a frozen suite.
- **A frozen protocol.** `arena suite freeze` hashes the suite and every source file that shapes a question or a
  score; test runs refuse a tree that differs. Every result records the lock, the checkpoint revision and a hash
  of its serving settings.
- **Verifiable.** Every decision is logged; `arena verify` replays each game and requires identical text,
  positions and score.

The full protocol is in [docs/methodology.md](docs/methodology.md).

## Scores

For each game, `k = clip((model - random) / (reference - random), 0, 1)` over the test seeds. A board's index is
100 x the mean of `k` over its games. Intervals come from a paired bootstrap over seeds (2000 replicates), and
pairwise differences carry Holm-adjusted p-values. The real-time board is scored against the frame board's anchors.

## Versus

The site's Versus pages compare two models on the same seed: both runs replay side by side in step (by decision on
the turn-based boards, by game step on the real-time board), with the signed score difference, each side's choice
probabilities, a comparison column and captions computed from the logs (first score, changes of lead, a run that
stops, a chase). Tetris on the frame and real-time boards is left out: no model clears a line there. Connect Four
is played directly between the models in suite `duel-v0.1` (every opening twice, colours swapped; `arena duel`),
rated by Bradley–Terry on the Elo scale. The rules are in [docs/methodology.md](docs/methodology.md#versus).

## Full runs

Freeze the suite, then `uv run arena campaign --seed-set test` runs everything in order: the anchors, then each
model alone on the GPU (macro and frame boards, `arena latency`, the real-time board, `arena bias`). It skips what is
done, retries failed episodes and moves past a model that keeps failing; `uv run arena status` shows what is left.
Finally `arena verify`, `arena env`, `arena score` and `arena export`, and `arena dataset` publishes the decision
logs as a Hugging Face dataset. [docs/operations.md](docs/operations.md) has the commands and the reasoning behind
the order.

## Adding a model

1. Add a component and a workflow to `model-compose.yml`. The workflow id is the player's name; pin the
   checkpoint revision. Any family model-compose serves under the `typed-decision` task works (clef, kev, laya,
   nimble); a new family needs a model-compose driver first and a two-line entry in `arena/families.py`.
2. `uv run python scripts/setup_runtimes.py <id>` and `uv run arena smoke --player <id>`.
3. `uv run arena campaign --seed-set test --models <id> --no-anchors`. Nobody else's score changes.

## Repository layout

```
model-compose.yml        the players (one workflow each) and the static web UI
suites/v0.1.toml         games, caps and seeds; suites/v0.1.lock.json once frozen
arena/                   the runner: games/, protocol, family adapters, episodes, scoring, replay, CLI
  games/                 tetris.py snake.py connect4.py (here), pong.py breakout.py (ALE), each with its reference
site/                    leaderboard and replay viewer (Vite, React); builds into webui/
webui/                   the built site and webui/data from `arena export`, served by model-compose
results/                 episode lines, scores, latency, environment (see results/README.md)
docs/                    methodology, suite, operations, design notes
tests/                   engines, protocol, runner, scoring, golden questions
scripts/                 serve.sh, setup_runtimes.py, model-compose.rev
```

Development checks: `uv run ruff check . && uv run mypy && uv run pytest`; for the site,
`pnpm --dir site install && pnpm --dir site check && pnpm --dir site build`.

## License

[MIT](LICENSE). Each model keeps its own license (all players above are Apache-2.0); the Atari ROMs ship with
ale-py under their own terms.
