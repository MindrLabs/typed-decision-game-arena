#!/usr/bin/env bash
# Serve every player (and the leaderboard) with the pinned model-compose revision (scripts/model-compose.rev).
#   scripts/serve.sh            API on :8380 (/api), leaderboard on :8381
# Override ports with ARENA_API_PORT / ARENA_WEB_PORT. Run scripts/setup_runtimes.py once before the first start.
set -euo pipefail
cd "$(dirname "$0")/.."
rev="$(tr -d '[:space:]' < scripts/model-compose.rev)"
exec uvx --python 3.12 --from "git+https://github.com/hanyeol/model-compose@${rev}" model-compose up "$@"
