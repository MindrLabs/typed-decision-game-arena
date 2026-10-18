# Common tasks; every recipe is a thin wrapper around the commands in README.md and docs/operations.md.

# lint, typecheck and test everything (Python and the site)
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    uv run pytest
    pnpm --dir site check

# format Python sources
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# one runtime per model, one at a time (once per machine)
setup:
    uv sync
    uv run python scripts/setup_runtimes.py

# models on :8380/api, leaderboard on :8381
serve:
    scripts/serve.sh

# rebuild the leaderboard into webui/ (keeps webui/data)
site:
    pnpm --dir site install --frozen-lockfile
    pnpm --dir site build

# dev-seed pilot: anchors, then each model's boards, latency and bias (resumable)
pilot models="laya-typed,kev-0.8b,clef-flash,nimble-v2":
    uv run arena campaign --seed-set dev --models {{models}}

# what is complete, per player and board
status seed_set="test":
    uv run arena status --seed-set {{seed_set}}

# refresh scores and the leaderboard data from a seed set (dev or test)
publish seed_set="test":
    uv run arena verify --seed-set {{seed_set}}
    uv run arena score --seed-set {{seed_set}}
    uv run arena export --seed-set {{seed_set}}

# decision logs and results to the Hugging Face dataset (a new one is private)
dataset seed_set="test":
    uv run --extra publish arena dataset --seed-set {{seed_set}}

# the README's tables and figures, recomputed from results/ (and the replays in webui/data)
report:
    uv run python scripts/stats.py
    uv run --extra report python scripts/charts.py

# direct Connect Four games between every pair of models (resumable; the largest model's pairs last)
duel seed_set="test":
    uv run arena duel run --seed-set {{seed_set}} --last clef

# replay and rate the direct games
duel-publish seed_set="test":
    uv run arena duel verify --seed-set {{seed_set}}
    uv run arena duel score --seed-set {{seed_set}}
