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

# dev-seed pilot of one player on the macro board
pilot player:
    uv run arena board --board macro --player {{player}} --seeds dev

# refresh scores and the leaderboard data from a seed set (dev or test)
publish seed_set="test":
    uv run arena verify --seed-set {{seed_set}}
    uv run arena score --seed-set {{seed_set}}
    uv run arena export --seed-set {{seed_set}}
