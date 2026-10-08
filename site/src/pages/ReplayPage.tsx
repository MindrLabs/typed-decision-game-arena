import { Suspense, use } from 'react'

import { ErrorBoundary } from '../components/ErrorBoundary'
import { DevelopmentBanner } from '../components/Layout'
import { Card } from '../components/ui'
import { replayResource } from '../lib/data'
import { findReplay, replaysOf } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, ReplayRef } from '../lib/types'
import { ReplayView } from '../replay/ReplayView'

function LoadedReplay({ index, reference }: { index: ArenaIndex; reference: ReplayRef }) {
  const replay = use(replayResource(reference.path))
  return <ReplayView index={index} replay={replay} />
}

export function ReplayPage({
  index,
  board,
  game,
  player,
  seed,
}: {
  index: ArenaIndex
  board: string
  game: string
  player: string
  seed: number
}) {
  const reference = findReplay(index, board, game, player, seed)
  if (!reference) {
    const others = replaysOf(index, { board, game })
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Replay not exported</h1>
        <p className="text-sm text-muted">
          There is no exported replay for {player} on {board}/{game}, seed {seed}. Exports keep a few seeds per player
          (<code className="font-mono">arena export --replays N</code>).
        </p>
        {others.length > 0 ? (
          <ul className="list-inside list-disc text-sm">
            {others.map((ref) => (
              <li key={ref.path}>
                <a href={href.replay(ref.board, ref.game, ref.player, ref.seed)}>
                  {index.players[ref.player]?.title ?? ref.player}, seed {ref.seed}
                </a>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <DevelopmentBanner index={index} />
      <ErrorBoundary
        key={reference.path}
        fallback={(error) => (
          <Card className="p-4">
            <p className="text-sm text-fg">The replay could not be loaded.</p>
            <p className="mt-1 font-mono text-xs text-muted">{error.message}</p>
          </Card>
        )}
      >
        <Suspense
          fallback={
            <p className="text-sm text-muted" role="status">
              Loading replay…
            </p>
          }
        >
          <LoadedReplay index={index} reference={reference} />
        </Suspense>
      </ErrorBoundary>
    </div>
  )
}
