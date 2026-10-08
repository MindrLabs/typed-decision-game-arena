# Results

```
results/<suite>/
  <seed set>/<board>/<game>/<player>/
    episodes.jsonl            one line per finished episode (committed for test seeds)
    decisions/<seed>.jsonl.gz every decision of an episode, then its end (git-ignored, see Publication)
    errors.jsonl              failed episodes; they run again on the next invocation (git-ignored)
  latency/<player>.json       arena latency
  bias/<player>.json          arena bias
  laya-cuts.json              arena laya-cuts
  environment.json            arena env
  scores-<seed set>.json      arena score
```

**Episode line**: `suite`, `lock` (digest of the frozen suite, test seeds only), `seed_set`, `board`, `game`,
`player`, `seed`, `score`, `metrics` (per game, e.g. `lines`, `pieces`, `topped_out`; `result`, `missed_wins`),
`decisions`, `forced` (single-option decisions, not asked), `calls` (requests sent), `steps` (game steps),
`delay_steps` (real-time board), `latency_ms` (`median`, `p95`, `n` over the episode's requests), `model`
(`family`, `repository`, `revision`, `base_model`, `preset`, `config_sha`), `arena` (version), `started`,
`seconds`.

**Decision line** (one per decision, gzipped JSONL): `i`, `step`, `snapshot` (the position, for replays),
`state`, `instructions`, `options` (`key`, `text`, canonical order), `calls` (each request: `stage`, `keys` in the
order shown, `choice`, `p` probabilities or null, `ms`), `choice`, `forced`. The last line of every log is
`{"final": true, "step": ..., "snapshot": ...}`, the position after the last move. Tetris macro snapshots also carry
`landings`: the cells of every landing on offer, keyed like the options.

**Latency and bias files** record the suite lock they were measured under (`lock`, null before the freeze). Test
seeds of the real-time board use only a latency measured under the current lock.

`uv run arena verify` replays decision logs against the engine; `uv run arena score` and `uv run arena export`
read only episode lines (and, for replays on the site, a few decision logs). `uv run arena status` shows what is
complete per player and board.

## Publication

Episode lines, scores, latency, bias and the environment record of the test seeds are committed here. The decision
logs go to the Hugging Face dataset
[`MindrLabs/typed-decision-game-arena`](https://huggingface.co/datasets/MindrLabs/typed-decision-game-arena)
with `uv run arena dataset --seed-set test`, together with the suite, its lock and everything above, in one commit
per upload. That dataset has the same layout as this directory, so `arena verify --results <dataset>` replays it.
