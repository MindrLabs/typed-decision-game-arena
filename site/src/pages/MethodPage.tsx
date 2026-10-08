import type { ReactNode } from 'react'

import { Card, Mono } from '../components/ui'
import type { ArenaIndex } from '../lib/types'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-5">
      <h2 className="mb-2 text-base font-semibold tracking-tight text-fg">{title}</h2>
      <div className="flex flex-col gap-2 text-sm leading-relaxed text-muted [&_strong]:font-semibold [&_strong]:text-fg">
        {children}
      </div>
    </Card>
  )
}

function Formula({ children }: { children: string }) {
  return <pre className="overflow-x-auto rounded-lg bg-surface-2 px-3 py-2 font-mono text-xs text-fg">{children}</pre>
}

export function MethodView({ index }: { index: ArenaIndex }) {
  const { suite } = index
  const confidence = Math.round(suite.confidence * 100)
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Method</h1>
        <p className="max-w-3xl text-sm text-muted">
          A summary of suite {suite.id}. The full rules, with the reasons behind them, are in <Mono>docs/methodology.md</Mono> of
          the repository; the numbers below come from the exported data.
        </p>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
        <Section title="What every model sees">
          <p>
            Each decision is one typed question sent to a model-compose <Mono>typed-decision</Mono> workflow (clef, kev and laya
            take it as a <Mono>choice</Mono> question, nimble as an <Mono>enum</Mono>): the game state as text, short instructions,
            and one sentence per legal option. <strong>Every model gets byte-identical sentences</strong>; only the JSON around them
            differs between model families. There is no per-model prompt tuning.
          </p>
          <p>
            Option texts state what the game shows and what a move does at once (lines a placement clears, the holes it leaves, a
            column that wins); nothing ranks, recommends or predicts.
          </p>
        </Section>
        <Section title="Option order and many options">
          <p>
            The engine lists options in an order that often means something (columns left to right). Every request instead shows a{' '}
            <strong>seeded shuffle</strong>, derived from the suite, board, game, seed and decision number but not from the player.
          </p>
          <p>
            More than <strong>{suite.group_size} options</strong> go through a knockout: balanced groups of at most {suite.group_size},
            one pick per group, then a final among the winners. A decision with a single legal option is not asked.
          </p>
        </Section>
        <Section title="Boards">
          <p>
            <strong>Macro</strong>: one decision per meaningful choice (where a piece lands, which band the paddle covers); a fixed
            controller does the low-level input. <strong>Frame</strong>: one decision per game step. Both wait for the player.
          </p>
          <p>
            <strong>Real-time</strong>: the frame games keep running while the player decides. A decision takes effect{' '}
            <Mono>ceil(median latency / 66.7 ms)</Mono> steps (at least one) after the position it was made from; in between, a
            paddle push stays pushed and a Tetris key acts once. Latency is measured with the model alone on the GPU, on fixed
            probe questions identical for every model.
          </p>
        </Section>
        <Section title="Scores">
          <p>Per game, a player's mean score over the seeds is placed between two anchors run on the same seeds:</p>
          <Formula>{'k = clip((mean − random) / (reference − random), 0, 1)\nindex = 100 × mean of k over the board’s games'}</Formula>
          <p>
            <strong>Random</strong> picks a legal option uniformly; the <strong>reference</strong> is a strong rule-based player
            that reads the game state directly. Games weigh equally. The real-time board uses the frame board's anchors: random
            play and the reference reacting instantly.
          </p>
        </Section>
        <Section title="Intervals and comparisons">
          <p>
            {confidence}% intervals come from a paired bootstrap with {suite.bootstrap.toLocaleString('en-US')} resamples: each
            resample draws the seeds of every game once and applies the same draw to every player and both anchors.
          </p>
          <p>
            Differences between models get two-sided bootstrap p-values, adjusted with Holm's method within each board. Whether two
            models differ is judged by that Holm-adjusted pairwise test, listed under each board, not by whether their intervals
            overlap.
          </p>
        </Section>
        <Section title="Reproducibility">
          <p>
            A suite is frozen by a lock file: the sha256 of the suite definition and of every source file that shapes a question or
            a score, plus the library versions. Test seeds run only against a matching lock{suite.frozen ? '' : ' (this suite is not frozen yet)'}.
          </p>
          <p>
            Every decision is logged (text, options in the order shown, probabilities, latency). Replays re-run the engine with the
            logged choices and must reproduce every question and score exactly. Atari games use ALE with sticky actions at{' '}
            {suite.sticky} and 4 frames per step (Machado et al., 2018).
          </p>
        </Section>
      </div>
    </div>
  )
}
