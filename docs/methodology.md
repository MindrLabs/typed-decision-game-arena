# Methodology

This is the protocol of suite v0.1: what a model reads, when it is asked, how its answer becomes a move, and how
moves become a score. Everything here is implemented in `arena/` and pinned by the suite lock (see
[Freezing](#freezing-and-verification)); the per-game details are in [suite-v0.1.md](suite-v0.1.md).

## What is measured

A typed-decision model takes a text and a list of allowed answers and returns one of them, with a probability for
each. It never writes free text. The arena turns a game into a sequence of such questions, one per decision, and
measures how well a model plays when every move it makes is one of its answers.

## Boards

| Board | Timing | One decision is | Games |
|---|---|---|---|
| Macro | turn-based | one meaningful choice: where a piece lands, which band the paddle covers, which way to turn, which column to play | Tetris, Snake, Connect Four, Pong, Breakout |
| Frame | turn-based | one step of the game: a key, or a push of the paddle | Tetris, Pong, Breakout |
| Real-time | the game keeps running while the model thinks | as on the frame board | Tetris, Pong, Breakout |

On the macro board a fixed controller turns the decision into low-level input (for example, it moves the paddle to
the chosen band). Snake and Connect Four have no finer level, so they appear on the macro board only.

## What a model sees

Every request carries three things, identical for every model:

- **state**: the position in plain text (boards drawn row by row, coordinates and motion for the Atari games);
- **instructions**: what is being chosen and the goal of the game;
- **options**: one sentence per legal move, under a short key.

The families served by model-compose declare a question differently, so only the JSON around those sentences
differs:

| Family | Question |
|---|---|
| clef, kev, laya | `{"move": {"type": "choice", "instructions": ..., "criteria": {key: sentence}}}` |
| nimble | `{"move": {"type": "enum", "choices": [key, ...], "description": ..., "choice_descriptions": {key: sentence}}}` |

There is no per-model prompt. Serving settings live in `model-compose.yml`; every result records the checkpoint,
its revision and a hash of the component's settings, so a result always points at the exact configuration that
produced it.

### What the text may contain

The state describes what the screen shows. Each option states what the move *is* and the facts that hold
immediately after it, and nothing else:

| Allowed | Not allowed |
|---|---|
| Tetris: the rotation and columns of a landing, the lines it clears, the holes and stack height right after | a ranking of landings, a shortlist, a heuristic score |
| Snake: the cell the head enters, and whether that cell is a wall, the body, food or empty | how much room is left behind the move |
| Connect Four: whether the move wins, whether it takes the cell where the opponent could complete four, whether it leaves the opponent an immediate four | the value of the position, a solver's verdict |
| Pong, Breakout: positions, how far the ball moved over the last steps, the band each option covers | where the ball will arrive, how far the paddle is from the ball |

The state also names every limit that can end the game, the arena's caps included (300 Tetris pieces, 200 Snake
steps without food, and so on), with the counters that run against them: a player is never stopped by a rule it
was not shown. Instructions state the goal of the game, not how to weigh the facts.

## Option order and the knockout

The engine lists options in a canonical order that often carries meaning (columns left to right, landings by
rotation). A model that leans on position would gain or lose systematically from that order, so no request uses
it: every decision shows its options in a seeded shuffle. The shuffle's seed comes from (suite, board, game, seed,
decision index) and not from the player, so two players at the same point of the same game see the same order.

A request shows at most **8 options** (`group_size`). A decision with more options goes through a knockout: the
shuffled options are split into the fewest groups of at most 8 with sizes differing by at most one, the model
picks one per group, and a final among the group winners (shuffled again) decides. A T piece in Tetris has 34
landings: five groups of 7, 7, 7, 7 and 6, then a final of five, six requests in all. Eight fits every family:
Laya's probabilities stop being calibrated from 11 options and its option head has a token budget, and the Nimble
loader that model-compose pins accepts at most 26 choices.

A decision with a single legal option is not asked; the move is played for every player alike and counted as
forced.

The move is the option the server returns (each family returns its most probable option). Probabilities are
logged for every request. `arena bias` measures how much a model follows position: it asks fixed probe questions
in one order and in the reverse order and reports how often the same option wins, and how often the first or last
shown option is picked against the rate a uniform pick would give.

## Timing

**Turn-based** (macro and frame boards): the game waits for every decision.

**Real-time** (real-time board): a model that observes the game at step *t* answers at step *t + k*, where
*k* = ceil(median latency / 66.7 ms), at least one step. 66.7 ms is one step of the frame games (4 frames at
60 Hz). Until the answer lands the game runs on what was decided before: a paddle push stays pushed, a Tetris key
acts once and is followed by waiting. Every decision therefore acts on a picture *k* steps old. The state text
ends with one line saying so and naming the previous choice that takes effect now, since a real-time player
knows what it decided last.

The latency is each model's median on the frame board's probe questions (`arena latency`): 200 fixed questions
per game taken from the reference player's games on probe seeds, after 20 warm-up requests, timed on the client
(model-compose's HTTP overhead included), with the model alone on the GPU. The file records the GPU and the other
GPU processes seen at the start, so a contaminated measurement is visible. Test seeds use only a latency measured
under the frozen suite, and scores are refused when a model's real-time episodes ran with another *k* than its
published latency gives. *k* is fixed per model, so the real-time board is as reproducible as the others, but it
belongs to the machine that measured it.

## Seeds

Each game has **dev** seeds (pilots and development) and **test** seeds (the published runs). They never overlap.
Test seeds only run against a frozen suite.

A seed fixes everything the player does not choose. Tetris pieces come from a seeded 7-bag that does not depend
on play. Snake's *k*-th food is the first free cell in a stream seeded by (seed, *k*), so all players meet the same
food unless their snake covers it. In Connect Four the seed picks the opponent from the ladder (random,
win-or-block, negamax at depth 4) and who moves first; any six consecutive seeds cover every pairing equally. Pong
and Breakout follow Machado et al. (2018): 4 frames per step and sticky actions with probability 0.25, seeded
through the emulator's reset. Sticky actions are what make Atari seeds differ: the console itself is
deterministic, and with `repeat_action_probability = 0` every seed replays the same game for a deterministic
player (`tests/test_atari.py` checks both facts).

## Anchors and scores

Every game has two anchor players, run on the same test seeds as the models:

- **random**: a uniformly random legal option (the 0 of every scale);
- **reference**: a strong rule-based player that reads the game state directly, never the text (the 100).

| Game | Reference player |
|---|---|
| Tetris (macro) | Dellacherie's features with the El-Tetris weights over the same landings the models choose from |
| Tetris (frame) | the same choice of landing, executed key by key and re-planned when blocked |
| Snake | shortest path to the food when the tail stays reachable after eating; otherwise the safe move that keeps the tail reachable, farthest from the food |
| Connect Four | negamax with alpha-beta at depth 7 |
| Pong, Breakout | predict where the ball meets the paddle line (bouncing off the walls); on the macro board pick the band containing it, on the frame board steer towards it with a model-predictive controller fitted to the paddle's measured dynamics |

For one game, with means over the test seeds,

    k = clip((model - random) / (reference - random), 0, 1)

and a board's **index** is 100 x the mean of *k* over its games, each game weighted equally. The real-time
board takes its anchors from the frame board: random play, and the reference reacting without delay. A model
cannot score above a reference on the index (clipped at 1); the references are chosen strong enough that this
should be rare, and raw scores are always reported next to *k*.

Because anchors are fixed players on fixed seeds, adding a model never changes another model's score.

**Intervals.** A paired bootstrap with 2000 replicates: each replicate resamples the seeds of every game once and
applies that same resample to every player and both anchors, then recomputes means, *k* and the index. Intervals
are the 2.5th and 97.5th percentiles. The resample indices come from the arena's own seeded stream, so a report
is reproducible to the last digit. For every pair of complete models, the index difference gets a two-sided
bootstrap p-value, adjusted with Holm's method within the board.

A player is ranked on a board only once it has every test seed of every game of that board.

## Freezing and verification

`arena suite freeze` writes `suites/v0.1.lock.json`: the sha256 of the suite file and of every source file that
shapes what a model reads or how a score comes about (`arena/core.py`, `seeding.py`, `protocol.py`,
`families.py`, `episode.py`, `tasks.py` and `arena/games/`), the versions of ale-py, gymnasium and numpy, and the
Python version. Test-seed runs refuse to start unless the working tree matches the lock, and every result line
records the lock's digest. Changing any of it after the freeze makes a new suite version, and every player runs
again.

Every decision is logged: the state, instructions and options, each request's shown order, choice,
probabilities and latency, and a snapshot of the position. `arena verify` replays each logged episode from its
seed and logged choices and requires every state text, option list and snapshot, and the final score, to match
byte for byte. `tests/golden/` pins the first question of every board and game, so any change to what models read
shows up as a diff. `arena env` records the GPU and driver, the model-compose revision, this repository's commit
and the full package list of every model runtime.

## Limitations

- The reference players are strong, not optimal. On Pong's macro board the reference still loses to the console's
  built-in opponent on average; it is far ahead of random play, which is what the scale needs.
- The option facts state immediate consequences. They spare a model from computing them, by design: the arena
  measures decisions, not arithmetic over a drawing of the board.
- Models answer one decision at a time and remember nothing between decisions except what the state says.
- Latency, and therefore the real-time board, is measured on one machine (an NVIDIA DGX Spark, GB10).
- model-compose's Laya driver loads the bundle repository without a revision, so Laya players are not pinned to
  a commit; the HF snapshot used is visible in `arena env`.
- Nimble 9B v2 is served by the Nimble loader that model-compose pins. For at most 26 choices its prompts are the
  release's own (A-Z codes); the released v2 loader only adds a probability temperature, which does not change
  which option comes first. Probabilities reported for Nimble are therefore unscaled.
- Text only: the models read no images.
