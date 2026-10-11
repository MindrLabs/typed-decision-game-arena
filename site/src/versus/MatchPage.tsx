import { Suspense, use, useMemo, useState } from 'react'

import { ErrorBoundary } from '../components/ErrorBoundary'
import { Card } from '../components/ui'
import { replayPath, replayResource, versusResource } from '../lib/data'
import { formatMs, formatNumber } from '../lib/format'
import { playerInfo } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, Replay, VersusData, VersusGame } from '../lib/types'
import { formatScore, gameKey, matchEvents, seedRows, seriesOf, seriesRecord, type Side } from '../lib/versus'
import { MatchView } from './MatchView'
import { Badge, TEAM, eventLabel } from './parts'

function TapeRow({ label, a, b, better }: { label: string; a: string; b: string; better: Side | null }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(6rem,14rem)_minmax(0,1fr)] items-center gap-2 border-t border-line py-2.5 sm:gap-4">
      <span className={`text-right font-mono text-xl font-bold tabular-nums ${better === 'a' ? TEAM.a.text : 'text-fg'}`}>{a}</span>
      <span className="text-center text-xs text-muted">{label}</span>
      <span className={`font-mono text-xl font-bold tabular-nums ${better === 'b' ? TEAM.b.text : 'text-fg'}`}>{b}</span>
    </div>
  )
}

function better(a: number | undefined, b: number | undefined, higher = true): Side | null {
  if (a === undefined || b === undefined || a === b) return null
  return a > b === higher ? 'a' : 'b'
}

function MatchIntro({
  index,
  data,
  game,
  seed,
  left,
  right,
  onWatch,
  hideResult,
  setHideResult,
  showProbabilities,
  setShowProbabilities,
}: {
  index: ArenaIndex
  data: VersusData
  game: VersusGame
  seed: number
  left: Replay
  right: Replay
  onWatch: () => void
  hideResult: boolean
  setHideResult: (value: boolean) => void
  showProbabilities: boolean
  setShowProbabilities: (value: boolean) => void
}) {
  const key = gameKey(game.board, game.game)
  const ids = { a: left.player, b: right.player }
  const names = { a: playerInfo(index, ids.a).title, b: playerInfo(index, ids.b).title }
  const scores = index.scores[game.board]?.players ?? {}
  const gameTitle = index.games[game.game]?.title ?? game.game
  const boardTitle = index.boards.find((b) => b.id === game.board)?.title ?? game.board
  const rows = seedRows(data, game.board, game.game, ids.a, ids.b)
  const record = seriesRecord(rows)
  const events = useMemo(() => matchEvents(seriesOf(left, game.sync), seriesOf(right, game.sync)), [left, right, game.sync])
  const par = data.par[key]?.[String(seed)]
  const value = (side: Side, pick: 'index' | 'mean' | 'latency'): number | undefined => {
    const player = scores[ids[side]]
    if (pick === 'index') return player?.index
    const entry = player?.games[game.game]
    return pick === 'mean' ? entry?.mean : entry?.latency_ms?.median_of_episode_medians
  }
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <a href={href.versus}>Versus</a> · {gameTitle} · {boardTitle} board · seed {seed}
      </nav>
      <Card className="flex flex-col gap-5 p-6">
        <h1 className="text-center text-sm font-semibold tracking-wide text-muted uppercase">
          {gameTitle} · {boardTitle} board · seed {seed}
        </h1>
        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2 sm:gap-4">
          {(['a', 'b'] as const).map((side) => (
            <div key={side} className={`flex min-w-0 flex-col gap-1 ${side === 'a' ? 'order-1 items-end text-right' : 'order-3 items-start'}`}>
              <span aria-hidden="true" className={`h-1.5 w-12 rounded-full ${TEAM[side].fill}`} />
              <h2 className="text-xl font-bold tracking-tight break-words sm:text-3xl">{names[side]}</h2>
              <span className="truncate font-mono text-xs text-muted">{playerInfo(index, ids[side]).repository ?? ids[side]}</span>
            </div>
          ))}
          <span aria-hidden="true" className="order-2 pb-1.5 text-lg font-bold text-faint">
            vs
          </span>
        </div>
        <div className="flex flex-col">
          <TapeRow label={`${boardTitle} index`} a={formatNumber(value('a', 'index'), 1)} b={formatNumber(value('b', 'index'), 1)} better={better(value('a', 'index'), value('b', 'index'))} />
          <TapeRow
            label={`${gameTitle}, mean over ${rows.length} seeds`}
            a={formatNumber(value('a', 'mean'), 2)}
            b={formatNumber(value('b', 'mean'), 2)}
            better={better(value('a', 'mean'), value('b', 'mean'))}
          />
          <TapeRow label={`Seeds won on this game (${record.draws} drawn)`} a={String(record.wins)} b={String(record.losses)} better={better(record.wins, record.losses)} />
          <TapeRow label="Time per request, median" a={formatMs(value('a', 'latency'))} b={formatMs(value('b', 'latency'))} better={null} />
          {game.board === 'realtime' ? (
            <TapeRow label="Reaction delay" a={`${left.delay_steps} steps`} b={`${right.delay_steps} steps`} better={better(left.delay_steps, right.delay_steps, false)} />
          ) : null}
        </div>
        <div className="flex flex-wrap justify-center gap-1.5">
          <Badge strong>Same seed · same harness · same option order</Badge>
          <Badge>Kept in step by {game.sync === 'step' ? 'game step' : game.unit}</Badge>
        </div>
        <p className="text-center text-xs text-muted">
          {par !== undefined ? `Par for this seed: the reference player scores ${formatScore(game.game, par)}. ` : ''}
          A seed goes to the higher score; {game.board === 'realtime' ? 'time counts as reaction delay on this board.' : 'time per move does not count on this board.'}
        </p>
      </Card>
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
        <button type="button" onClick={onWatch} className="inline-flex h-12 items-center gap-2 rounded-xl bg-accent px-5 font-bold text-white dark:text-[var(--bg)]">
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="currentColor">
            <path d="M7 5l12 7-12 7z" />
          </svg>
          Watch from the start
        </button>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={hideResult}
            onChange={(event) => {
              setHideResult(event.target.checked)
            }}
            className="size-4 accent-[var(--accent)]"
          />
          Hide the result until the end
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showProbabilities}
            onChange={(event) => {
              setShowProbabilities(event.target.checked)
            }}
            className="size-4 accent-[var(--accent)]"
          />
          Show choice probabilities
        </label>
        <details className="basis-full text-sm">
          <summary className="flex min-h-11 items-center font-semibold">Chapters (shows what happens)</summary>
          <ol className="mt-1 flex list-decimal flex-col gap-1 pl-5 text-muted">
            {events
              .filter((e) => e.kind !== 'chase')
              .map((event, i) => (
                <li key={i}>{eventLabel(event, names, game.unit)}</li>
              ))}
          </ol>
        </details>
      </Card>
    </div>
  )
}

function LoadedMatch({ index, data, game, a, b, seed }: { index: ArenaIndex; data: VersusData; game: VersusGame; a: string; b: string; seed: number }) {
  const left = use(replayResource(replayPath(game.board, game.game, a, seed)))
  const right = use(replayResource(replayPath(game.board, game.game, b, seed)))
  const [watching, setWatching] = useState(false)
  const [hideResult, setHideResult] = useState(true)
  const [showProbabilities, setShowProbabilities] = useState(true)
  if (!watching) {
    return (
      <MatchIntro
        index={index}
        data={data}
        game={game}
        seed={seed}
        left={left}
        right={right}
        onWatch={() => {
          setWatching(true)
        }}
        hideResult={hideResult}
        setHideResult={setHideResult}
        showProbabilities={showProbabilities}
        setShowProbabilities={setShowProbabilities}
      />
    )
  }
  return <MatchView index={index} data={data} game={game} seed={seed} left={left} right={right} showProbabilities={showProbabilities} hideResult={hideResult} />
}

export function Missing({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-muted">{children}</p>
      <p className="text-sm">
        <a href={href.versus}>Back to Versus</a>
      </p>
    </div>
  )
}

export function MatchPage({ index, board, game, a, b, seed }: { index: ArenaIndex; board: string; game: string; a: string; b: string; seed: number }) {
  const data = use(versusResource())
  const spec = data.games.find((g) => g.board === board && g.game === game)
  if (!spec) {
    const excluded = data.excluded.find((g) => g.board === board && g.game === game)
    return <Missing title="Not compared">{excluded?.reason ?? `${board}/${game} is not one of the Versus games.`}</Missing>
  }
  const episodes = data.episodes[gameKey(board, game)] ?? {}
  if (a === b || !episodes[a]?.[String(seed)] || !episodes[b]?.[String(seed)]) {
    return <Missing title="No such match">Both models need a run of seed {seed} on this game, and they must differ.</Missing>
  }
  return (
    <ErrorBoundary
      fallback={(error) => (
        <Missing title="The replays could not be loaded">
          {error.message}. Write them with <code className="font-mono">uv run arena export --seed-set test</code>.
        </Missing>
      )}
    >
      <Suspense
        fallback={
          <p className="text-sm text-muted" role="status">
            Loading both runs…
          </p>
        }
      >
        <LoadedMatch key={`${board}/${game}/${a}/${b}/${seed}`} index={index} data={data} game={spec} a={a} b={b} seed={seed} />
      </Suspense>
    </ErrorBoundary>
  )
}
