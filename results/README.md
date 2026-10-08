# Results

```
results/<suite>/
  <seed set>/<board>/<game>/<player>/
    episodes.jsonl            one line per finished episode (committed for test seeds)
    decisions/<seed>.jsonl.gz every decision of an episode, then its end (git-ignored, published separately)
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

`uv run arena verify` replays decision logs against the engine; `uv run arena score` and `uv run arena export`
read only episode lines (and, for replays on the site, a few decision logs).
