# Suite v0.1

The games, what each decision looks like, and how each game is scored. Parameters live in
[`suites/v0.1.toml`](../suites/v0.1.toml); the protocol around them is in [methodology.md](methodology.md). The
first question of every board and game, exactly as models receive it, is in [`tests/golden/`](../tests/golden).
`uv run arena show --board <board> --game <game> --seed <seed> --skip <n>` prints any later one.

Status: **not frozen.** The numbers below may still change after the dev-seed pilot; once
`suites/v0.1.lock.json` exists they are fixed.

## Overview

| Board / game | Decision | Options | Ends | Score | Test seeds |
|---|---|---|---|---|---|
| macro / tetris | each piece | every reachable landing (9 to 34) | 300 pieces or top-out | lines cleared | 1-50 |
| macro / snake | each step | turn left, go straight, turn right | death, 1000 steps, or 200 steps without food | food eaten | 1-50 |
| macro / connect4 | each own move | legal columns (up to 7) | win, loss or full board | 1 win, 0.5 draw, 0 loss | 1-60 |
| macro / pong | ball changes direction | 8 bands of 20 pixels | game over (21 points) or 20,000 steps | points won minus lost | 1-20 |
| macro / breakout | ball changes direction | 8 bands of 18 pixels | game over (5 lives) or 10,000 steps | game points | 1-20 |
| frame / tetris | each step | left, right, cw, ccw, soft, hard, wait (legal ones) | 100 pieces or top-out | lines cleared | 1-30 |
| frame / pong | each step | up, down, stay | game over or 1500 steps | points won minus lost | 1-20 |
| frame / breakout | each step | left, right, stay (+ launch with no ball) | game over, 1500 steps, or 300 steps in a row without a ball in play | game points | 1-20 |

The real-time board plays the frame games with the player's reaction delay.

Every state names the limits that can end its game, the arena's caps included, with the counters that run
against them (the step, the pieces placed, the steps since the last food, the steps left to launch a ball), so no
player is stopped by a rule it was not shown.

Anchor means on the dev seeds (pilot, 3 to 6 seeds each):

| Board / game | random | reference |
|---|---|---|
| macro / tetris | 0 | 118.2 |
| macro / snake | 0 | 61.4 |
| macro / connect4 | 0.167 | 0.917 |
| macro / pong | -20.7 | -7.7 |
| macro / breakout | 0.7 | 55.3 |
| frame / tetris | 0 | 38.7 |
| frame / pong | -20.3 | 0.0 |
| frame / breakout | 0.7 | 224.3 |

## Tetris

A 10 x 20 well. SRS piece shapes, basic rotation without wall kicks, a seeded 7-bag, one next piece shown, no
hold. Text numbers rows from the bottom (row 1) and columns from the left (column 1); runs of empty rows are
written as one line, so the text stays short and loses nothing.

- **Macro.** The options are every distinct landing the piece can reach by rotating and shifting at spawn height
  and then hard-dropping; landings that cover the same cells are one option. Each option names the rotation, the
  columns and rows it lands in, the lines it clears, and the holes and stack height right after. Keys look like
  `cw-c4` (rotation, leftmost column).
- **Frame.** One key per step; the piece falls one row every 2 steps and locks when it cannot fall. Only keys that
  change something are offered, plus `wait` and `hard`. `hard` and a locking `soft` describe the landing they
  cause, in the same words as the macro options. The state marks the falling piece with `@`.
- **Reference.** Dellacherie's features (landing height, eroded cells, row and column transitions, holes, wells)
  weighted as in El-Tetris.

## Snake

A 10 x 10 grid; the snake starts with length 3 heading up. Moves are relative (turn left, go straight, turn right).
Each option names the cell the head enters and what is there: the body (the tail cell counts as free when the snake
does not grow), food, or nothing; a move into a wall says that the head would leave the grid. The state shows the
grid with `H` head, `o` body, `t` tail and `*` food.

- **Reference.** Shortest path to the food when, after eating, the head can still reach the tail; otherwise the
  safe move that keeps the tail reachable and stays farthest from the food; otherwise the move with the most room.

## Connect Four

7 columns x 6 rows against a fixed opponent ladder: random, win-or-block (wins if it can, blocks an immediate
four otherwise, random otherwise) and negamax at depth 4. The seed picks the opponent and who moves first.

Each option names the column and the row the disc lands in, and states whether it wins, whether it takes the cell
where the opponent could complete four, and whether it leaves the opponent an immediate four. Metrics also count
missed wins and moves that allow an immediate loss when a safe move existed.

- **Reference.** Negamax with alpha-beta at depth 7 and an open-lines evaluation.

## Pong

ALE `Pong-v5`; the player holds the right paddle against the console. Field coordinates: x 0-159, y 0-159 from
the top of the playing field. The player's paddle is at x 140-143 and 16 pixels tall. The state gives the score,
the ball's position and how far it moved over the last one or two steps (two only when they agree in direction,
so a bounce never blurs the reading), and both paddles' spans. Before the first serve the console keeps a
half-set ball and an opponent paddle above the field in memory; the state says that no ball is in play and that
the opponent's paddle is not on the field, as the screen shows.

- **Macro.** A decision whenever the ball starts moving towards the player, bounces off the top or bottom on its
  way in, or starts moving away, each time once three consistent steps show the new direction. The options are 8
  bands of 20 pixels; the controller moves the paddle centre to the middle of the chosen band and holds it there.
  Centred there, the 16-pixel paddle plus the 4-pixel ball covers the band.
- **Frame.** Push up, push down, or do not push. The paddle keeps some speed between steps.
- **Reference.** Predicts where the ball meets the paddle line, folding its path at the top and bottom edges. The
  frame reference steers with a 4-step model-predictive controller built on the paddle's measured dynamics
  (velocity' = 0.55 velocity + 10 per pushed step).

## Breakout

ALE `Breakout-v5`. Field coordinates: x 0-143 between the side walls, y 0 under the top wall; the paddle's top
edge is at y 157 and it is 16 pixels wide (8 once it shrinks; the state reports its current span). The state
shows the score, lives, ball position and motion, the paddle span, and the six brick rows with their point values
(7, 7, 4, 4, 1, 1).

- **Macro.** A decision whenever the ball starts falling or rising, or bounces off a side wall while falling. The
  options are 8 bands of 18 pixels (the paddle plus the ball); the controller centres the paddle in the chosen
  band and launches new balls by itself.
- **Frame.** Push left, push right, do not push, and launch while no ball is in play. A push moves the paddle
  about 12 pixels in its step and 11 more in the next. The game ends after 300 steps in a row without a ball in
  play: nothing happens until a ball is launched, and in the pilot a model that never launched spent all 1500
  steps that way (the state counts down the steps left).
- **Reference.** As in Pong, with the walls on the sides; a 3-step model-predictive controller for the frame board.
