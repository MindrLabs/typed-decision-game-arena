# Operations

How to run the benchmark end to end on one machine. Every command is resumable: re-running it continues where it
stopped.

## Once per machine

```bash
uv sync                                   # the runner's environment (.venv)
uv run python scripts/setup_runtimes.py   # one model-compose runtime per player under .runtime/, one at a time
```

`setup_runtimes.py` starts each component alone once. model-compose starts all components together, and on a first
start the components of one family install the same GitHub package out of one shared clone directory at the same
time, which can fail. After this step `scripts/serve.sh` finds everything installed and starts in seconds. No model
weights are downloaded here; each model downloads on its first request.

## Serving

```bash
scripts/serve.sh            # API http://127.0.0.1:8380/api, leaderboard http://127.0.0.1:8381
```

The model-compose revision is pinned in `scripts/model-compose.rev`. Ports: `ARENA_API_PORT`, `ARENA_WEB_PORT`; the
runner reads the API address from `--server`. Models load on their first request and unload after 120 idle seconds
(model-compose's `on_demand`; unloading also empties the CUDA cache), so all players can be declared while only the
one being run uses memory.

**One model at a time.** Models sharing the GPU slow each other down (on the GB10 a model measured 2.5 to 10 times
slower next to busy neighbours). That only costs time on the turn-based boards, but it would distort latency and
therefore the real-time board. Run one player, then the next.

Check a player end to end before a long run (one request per game):

```bash
uv run arena smoke --player kev-0.8b
```

## Order of a full run

1. **Pilot on dev seeds** (results stay local; `results/*/dev/` is git-ignored):
   ```bash
   uv run arena board --board macro --player random --seeds dev --workers 8
   uv run arena board --board macro --player reference --seeds dev --workers 8
   uv run arena board --board macro --player kev-0.8b --seeds dev
   uv run arena score --seed-set dev
   ```
   Adjust only parameters in `suites/v0.1.toml` and only on dev seeds. Regenerate the golden questions if the text
   changed (`UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`) and review the diff, then check that every Laya
   player still reads whole questions (`uv sync --extra diag && uv run arena laya-cuts`; with the 2048 / 512
   budgets nothing was cut on 2026-10-08).
2. **Freeze**: `uv run arena suite freeze`, commit `suites/v0.1.lock.json`. From now on the protocol is fixed.
3. **Anchors** on test seeds (CPU only; parallel is fine):
   ```bash
   for board in macro frame; do for p in random reference; do
     uv run arena board --board $board --player $p --seeds test --workers 8; done; done
   ```
4. **Models**, one at a time, macro and frame boards, then latency, then the real-time board:
   ```bash
   P=kev-0.8b
   uv run arena board --board macro --player $P --seeds test
   uv run arena board --board frame --player $P --seeds test
   uv run arena latency --player $P          # alone on the GPU
   uv run arena board --board realtime --player $P --seeds test
   uv run arena bias --player $P
   ```
5. **Check and publish**:
   ```bash
   uv run arena verify --seed-set test       # replays every episode
   uv run arena env                          # GPU, driver, model-compose revision, runtime packages
   uv run arena score --seed-set test        # results/v0.1/scores-test.json
   uv run arena export --seed-set test       # webui/data for the leaderboard
   ```

Long runs outlive a terminal: start them with `systemd-run --user --unit=<name> --working-directory=$PWD -E PATH=$PATH ...`
and follow `journalctl --user -u <name> -f`.

## Cost

Requests per episode depend on the game (Tetris landings above 8 options take several requests: on average about
4.7 per piece). Measured on the GB10 with the server warm: Laya about 30 ms per request, Kev 0.8B 60 to 100 ms,
Nimble 9B about 250 ms. An upper bound for one model over every test seed of the macro and frame boards is about
230,000 requests; most models end games far earlier than the caps.

## Results layout

See [`results/README.md`](../results/README.md). Episode lines and scores are small and belong in git; decision
logs are git-ignored and published separately (for example as a dataset), since the replays on the site only need
a few of them.

## Troubleshooting

- **A component fails on the first start** with a failed `uv pip install ... mindor-git-sources ...`: run
  `scripts/setup_runtimes.py` (see above).
- **`workflow ... is not served`**: the player id is not in `model-compose.yml`, or the server runs another file.
- **Test seeds refuse to run**: `uv run arena suite check` lists what differs from the lock.
- **The real-time board refuses a player**: measure its latency first (`arena latency`).
- **An episode failed**: it is in `errors.jsonl`; re-running the same command runs it again from the start.
