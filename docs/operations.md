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
time, which can fail ([hanyeol/model-compose#37](https://github.com/hanyeol/model-compose/issues/37)). After this
step `scripts/serve.sh` finds everything installed and starts in seconds. No model weights are downloaded here;
each model downloads on its first request (Clef's 55 GB take minutes, well inside the runner's 15-minute timeout,
and latency measurements warm up first).

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

For a campaign of several days, run the server as a user service that restarts after a crash; the campaign waits up
to an hour for it to come back:

```bash
systemd-run --user --unit=arena-serve -p Restart=on-failure --working-directory=$PWD -E PATH=$PATH scripts/serve.sh
systemctl --user stop arena-serve         # stops it and every model runtime
```

## Order of a full run

`arena campaign` runs everything of a seed set in this order, skips what is already done, retries failed
episodes, and moves on past a model that keeps failing (`arena status` shows what is left; running the same command
again picks it up):

1. the anchors, random and reference, on the macro and frame boards (CPU only, eight processes);
2. each model in turn: macro and frame boards; latency, once no other model holds more than an idle context on the
   GPU; the real-time board, which needs that latency; position bias.

Steps:

1. **Pilot on dev seeds** (results stay local; `results/*/dev/` is git-ignored):
   ```bash
   uv run arena campaign --seed-set dev --models laya-typed,kev-0.8b,clef-flash,nimble-v2
   uv run arena score --seed-set dev
   ```
   Adjust only parameters in `suites/v0.1.toml` and only on dev seeds. Regenerate the golden questions if the text
   changed (`UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`) and review the diff, then check that every Laya
   player still reads whole questions (`uv sync --extra diag && uv run arena laya-cuts`; with the 2048 / 512
   budgets nothing was cut on 2026-10-08).
2. **Freeze**: `uv run arena suite freeze`, commit `suites/v0.1.lock.json`. From now on the protocol is fixed.
   Latency and bias measured before the freeze do not count on test seeds: the campaign measures them again.
3. **The test campaign**, from a worktree at the frozen commit, so that later edits to the checkout cannot reach a
   run that lasts days (processes the campaign starts import the code from disk). Results go to the main checkout:
   ```bash
   git worktree add ../arena-run HEAD && cd ../arena-run && uv sync
   systemd-run --user --unit=arena-campaign --working-directory=$PWD -E PATH=$PATH \
     uv run arena campaign --seed-set test --results ~/Projects/typed-decision-game-arena/results \
       --models laya-multilingual,laya-english,laya-typed,kev-0.8b,kev-4b,clef-flash,nimble-v2,nimble,kev-9b,clef
   journalctl --user -u arena-campaign -f    # follow it
   uv run arena status --seed-set test       # what is complete
   ```
   Fastest models first, so the board fills early. To give the GPU to something else, `systemctl --user stop
   arena-campaign`: the episodes that were running are discarded and run again on the next start.
4. **Check and publish**, from the main checkout:
   ```bash
   uv run arena verify --seed-set test       # replays every episode
   uv run arena env                          # GPU, driver, model-compose revision, packages of every runtime
   uv run arena score --seed-set test        # results/v0.1/scores-test.json
   uv run arena export --seed-set test       # webui/data for the leaderboard
   uv sync --extra publish && uv run arena dataset --seed-set test
   ```
   `arena dataset` uploads the decision logs with the suite, the episode lines, the diagnostics and the scores to
   the Hugging Face dataset `MindrLabs/typed-decision-game-arena` in one commit (a new dataset is private). Then
   commit `results/v0.1/` (episode lines, scores, latency, bias, environment) and `webui/data`.

## Asking the models again

`scripts/recheck.py` plays seed 1 of every board and game once more with every model, into a scratch directory, and
compares each decision with the published log: the question, the order each request showed, every pick and every
probability. It also records each runtime's GPU memory and peak resident memory. With the model server running:

```bash
uv run python scripts/recheck.py --out /tmp/recheck \
  --models laya-multilingual,laya-english,laya-typed,kev-0.8b,clef-flash,kev-4b,nimble-v2,nimble,kev-9b
systemctl --user restart arena-serve       # Clef last, on a freshly started server
uv run python scripts/recheck.py --out /tmp/recheck --models clef
```

It waits before each model until no model holds the GPU, so every model starts alone. The summary is merged into
`results/v0.1/recheck.json`; on 2026-10-18 all 110 games came out the same, every probability to the last digit.

## Direct games

The duel suite has its own lock (`suites/duel-v0.1.lock.json`, which also locks `arena/duel.py`). A pair needs both
models loaded at once, so the run waits before each pair until no other model holds the GPU (or 64 GiB is free
anyway), and loads the pair's models one at a time with an untimed request (Clef, 52 GB, takes about a quarter of an
hour on the GB10 while other work holds memory). Run the largest model's pairs last, so it stays loaded across them.
Clef's load peaks near 100 GB (the 52 GB on the GPU plus a CPU copy of about the same size), so start its pairs on a
freshly started model server: the runtimes of the models played before keep a few GB each. If the server is killed
for memory mid-load, restart it and run the same command again; finished games are kept.

```bash
systemd-run --user --unit=arena-duel --working-directory=$PWD -E PATH=$PATH \
  uv run arena duel run --seed-set test --last clef
uv run arena duel status --seed-set test     # games per pair
uv run arena duel verify --seed-set test     # replays every game
uv run arena duel score --seed-set test      # results/duel-v0.1/scores-test.json
uv run arena export --seed-set test          # also writes the Versus data and every replay it opens
```

If the leaderboard is already served on port 8381, start the model server with `ARENA_WEB_PORT=8382`.

## Cost

Requests per episode depend on the game (Tetris landings above 8 options take several requests: on average about
4.7 per piece). Measured on the GB10 with the server warm: Laya 15 to 30 ms per request, Kev 0.8B 75 to 100 ms,
Nimble 9B about 250 ms. An upper bound for one model over every test seed of the macro and frame boards is about
230,000 requests; most models end games far earlier than the caps. The real-time board costs about 1/k of the frame
board, since a model with a reaction time of k steps decides once every k steps.

## Results layout

See [`results/README.md`](../results/README.md). Episode lines and scores are small and belong in git; decision
logs are git-ignored and published as a Hugging Face dataset (`arena dataset`), since the replays on the site only
need a few of them.

## Troubleshooting

- **A component fails on the first start** with a failed `uv pip install ... mindor-git-sources ...`: run
  `scripts/setup_runtimes.py` (see above).
- **`workflow ... is not served`**: the player id is not in `model-compose.yml`, or the server runs another file.
- **Test seeds refuse to run**: `uv run arena suite check` lists what differs from the lock.
- **The real-time board refuses a player**: measure its latency first (`arena latency`). On test seeds it must have
  been measured under the current lock.
- **`arena score` refuses a real-time board** because its episodes ran with another delay than the latency file
  gives: the latency was measured again after the runs. Rerun that player's real-time board, or restore the file.
- **The campaign stopped with "no model server"**: the server was away for over an hour. Start it and run the same
  command again.
- **An episode failed**: it is in `errors.jsonl`; re-running the same command runs it again from the start.
