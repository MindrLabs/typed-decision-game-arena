import { useCallback, useEffect, useMemo, useState } from 'react'

import { playerInfo } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, Cell, Replay, ReplayDecision, VersusData, VersusGame } from '../lib/types'
import {
  captionAt,
  countsFromOne,
  currentLabel,
  diffPaths,
  endsTheGame,
  formatScore,
  framesOf,
  gameKey,
  matchEvents,
  ordinal,
  positionOf,
  scoreAt,
  seedRows,
  seriesOf,
  seriesRecord,
  shownEvents,
  sideAt,
  snakeTarget,
  styleOf,
  tetrisStack,
  topOptions,
  type MatchEvent,
  type Series,
  type Side,
  type SideView,
} from '../lib/versus'
import { GameCanvas } from '../replay/GameCanvas'
import { usePalette } from '../replay/palette'
import type { Candidate } from '../replay/renderers'
import { Badge, CaptionBox, DecisionCard, LowerRow, MirrorRow, TEAM, TeamDot, Timeline, eventLabel, percent } from './parts'

const SPEEDS = [1, 2, 4, 8, 15, 30, 60, 120] as const
const BOARD_WIDTH: Record<string, number> = { tetris: 250, snake: 280, pong: 288, breakout: 252 }

function defaultSpeed(game: VersusGame): number {
  if (game.board !== 'macro') return 30
  return game.game === 'tetris' ? 4 : 8
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'SUMMARY', 'A'].includes(target.tagName) || target.isContentEditable
}

function record(snapshot: unknown): Record<string, unknown> {
  return typeof snapshot === 'object' && snapshot !== null ? (snapshot as Record<string, unknown>) : {}
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

interface Run {
  side: Side
  id: string
  name: string
  replay: Replay
  series: Series
  positions: number[]
  /** How the run ended (versus.json), e.g. "topped out". */
  end: string
  delay: number
}

function candidatesOf(game: string, decision: ReplayDecision | null, snapshot: unknown): Candidate[] | undefined {
  if (!decision || decision.forced) return undefined
  const options = topOptions(decision)
  if (game === 'tetris') {
    const landings = record(snapshot).landings as Record<string, Cell[]> | undefined
    if (!landings) return undefined
    return options.flatMap((o, i) => (landings[o.key] ? [{ cells: landings[o.key] ?? [], rank: i + 1 }] : []))
  }
  if (game === 'snake') {
    return options.flatMap((o, i) => {
      const target = snakeTarget(o.text)
      return target ? [{ cells: [target], rank: i + 1, danger: endsTheGame(o.text) }] : []
    })
  }
  return undefined
}

function Ribbon({ run, index }: { run: Run; index: number }) {
  const recent = run.replay.decisions.slice(Math.max(0, index - 119), index + 1)
  const up = run.replay.game === 'pong' ? 'u' : 'l'
  const down = run.replay.game === 'pong' ? 'd' : 'r'
  const words = run.replay.game === 'pong' ? ['up', 'down'] : ['left', 'right']
  return (
    <div className="flex flex-col gap-1">
      <div aria-hidden="true" className="relative flex h-10 overflow-hidden rounded-md bg-surface-2">
        <span className="absolute inset-x-0 top-5 h-px bg-line" />
        {recent.map((d) => {
          const final = d.calls.at(-1)
          const p = final?.p?.[d.choice] ?? 1
          const key = d.choice.charAt(0)
          const height = `${(p * 19).toFixed(1)}px`
          return (
            <span key={d.i} className="relative min-w-px flex-1">
              {key === up ? (
                <span className={`absolute inset-x-0 bottom-5 ${TEAM[run.side].fill}`} style={{ height }} />
              ) : key === down ? (
                <span className={`absolute inset-x-0 top-5 opacity-70 ${TEAM[run.side].fill}`} style={{ height }} />
              ) : (
                <span className="absolute inset-x-0 top-[19px] h-[3px] bg-faint" />
              )}
            </span>
          )
        })}
      </div>
      <span className="text-[11px] text-muted">
        Last {recent.length} decisions: {words[0]} above the line, {words[1]} below, stay on it; height is the choice probability
      </span>
    </div>
  )
}

function heroLine(game: string, view: SideView): string {
  const s = record(view.snapshot)
  if (game === 'tetris') return `${Number(s.pieces ?? 0)} pieces`
  if (game === 'snake') return `length ${Array.isArray(s.snake) ? s.snake.length : 0}`
  if (game === 'pong') {
    const score = Array.isArray(s.score) ? (s.score as number[]) : [0, 0]
    return `points ${score[0] ?? 0} to ${score[1] ?? 0} against the CPU`
  }
  if (game === 'breakout') return `${Number(s.lives ?? 0)} lives · ${bricksBroken(s)} bricks`
  return ''
}

function bricksBroken(s: Record<string, unknown>): number {
  const rows = Array.isArray(s.bricks) ? (s.bricks as string[]) : []
  return rows.reduce((total, row) => total + row.split('.').length - 1, 0)
}

function SidePanel({
  run,
  view,
  score,
  game,
  unit,
  other,
  chased,
  showProbabilities,
  next,
  onNext,
}: {
  run: Run
  view: SideView
  score: number
  game: VersusGame
  unit: string
  other: Run
  chased: boolean
  showProbabilities: boolean
  next: boolean
  onNext: (next: boolean) => void
}) {
  const left = run.side === 'a'
  const shown = next && view.decision ? (run.replay.decisions[view.index + 1] ?? null) : view.decision
  return (
    <section
      aria-label={`${run.name}: ${view.ended ? 'finished' : 'deciding'}`}
      className={`flex min-w-0 flex-1 basis-56 flex-col gap-2.5 ${left ? 'order-1 text-right' : 'order-5 text-left'} max-w-72`}
    >
      <div className={`flex flex-col ${left ? 'items-end' : 'items-start'}`}>
        <span className="text-xs text-muted">{game.game === 'pong' ? 'Margin' : capital(game.game === 'tetris' ? 'lines' : game.game === 'snake' ? 'food' : 'score')}</span>
        <span className={`font-mono text-4xl leading-none font-bold tabular-nums ${TEAM[run.side].text}`}>{formatScore(game.game, score)}</span>
        <span className="text-xs text-muted">{heroLine(game.game, view)}</span>
      </div>
      {view.ended ? (
        <div className={`flex flex-col gap-1 rounded-xl border border-line bg-surface-2 p-3 ${left ? 'items-end' : 'items-start'}`}>
          <span className="inline-flex items-center gap-1.5 font-semibold">
            <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4 text-danger" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M9 9l6 6M15 9l-6 6" />
            </svg>
            Out
          </span>
          <span className="text-sm text-muted">
            {capital(run.end || 'stopped')} at {unit} {run.series.end} with {formatScore(game.game, run.series.final)}.
            {chased ? ` Its score is ${other.name}'s target.` : ''}
          </span>
        </div>
      ) : shown ? (
        <>
          <div role="group" aria-label="Which decision" className="flex gap-1">
            {[false, true].map((value) => (
              <button
                key={String(value)}
                type="button"
                aria-pressed={next === value}
                onClick={() => {
                  onNext(value)
                }}
                className={`h-8 flex-1 rounded-md text-xs ${next === value ? 'bg-surface-2 font-semibold text-fg' : 'border border-line text-muted'}`}
              >
                {value ? 'Next one' : 'Made here'}
              </button>
            ))}
          </div>
          <DecisionCard
            side={run.side}
            decision={shown}
            title={currentLabel(unit, positionOf(shown, game.sync))}
            showProbabilities={showProbabilities}
          />
        </>
      ) : null}
    </section>
  )
}

function Board({ run, view, game, showProbabilities }: { run: Run; view: SideView; game: VersusGame; showProbabilities: boolean }) {
  const palette = usePalette()
  const colour = run.side === 'a' ? palette.teamA : palette.teamB
  const candidates = showProbabilities && !view.ended ? candidatesOf(game.game, view.decision, view.snapshot) : undefined
  const ribbon = game.board !== 'macro' && (game.game === 'pong' || game.game === 'breakout')
  return (
    <div className={`flex shrink-0 flex-col gap-2 ${run.side === 'a' ? 'order-2' : 'order-4'}`} style={{ width: BOARD_WIDTH[game.game] ?? 260 }}>
      <div className="relative rounded-xl border border-line bg-surface p-1.5">
        <div className={view.ended ? 'opacity-45' : ''}>
          <GameCanvas
            game={game.game}
            snapshot={view.snapshot}
            label={`${run.name}${view.ended ? ', finished' : ''}`}
            candidates={candidates}
            candidateColour={colour}
          />
        </div>
      </div>
      {ribbon && !view.ended ? <Ribbon run={run} index={view.index} /> : null}
    </div>
  )
}

function stateCallout(events: readonly MatchEvent[], position: number, game: string, runs: Record<Side, Run>, sa: number, sb: number) {
  const chase = events.find((e) => e.kind === 'chase' && e.position <= position)
  const ended = position >= runs.a.series.end && position >= runs.b.series.end
  if (chase?.side && !ended) {
    const survivor = chase.side
    const current = survivor === 'a' ? sa : sb
    const gap = (chase.target ?? 0) - current
    return {
      side: survivor,
      kind: 'Chase',
      headline: gap >= 0 ? `${runs[survivor].name} needs ${gap + 1} more to win` : `${runs[survivor].name} has passed the target`,
      note: `Target: ${formatScore(game, chase.target ?? 0)} from ${runs[survivor === 'a' ? 'b' : 'a'].name}.`,
    }
  }
  const changes = events.filter((e) => e.kind === 'lead' && e.position <= position).length
  if (sa === sb) return { side: null, kind: ended ? 'Final' : 'Level', headline: ended ? 'A draw' : 'Level', note: changes ? `${capital(ordinal(changes))} change of lead so far.` : 'No lead change so far.' }
  const side: Side = sa > sb ? 'a' : 'b'
  return {
    side,
    kind: ended ? 'Final' : changes ? 'Lead' : 'Ahead',
    headline: ended ? `${runs[side].name} wins by ${Math.abs(sa - sb)}` : `${runs[side].name} ahead by ${Math.abs(sa - sb)}`,
    note: changes ? `${capital(ordinal(changes))} change of lead so far.` : 'The lead has not changed hands.',
  }
}

export function MatchView({
  index,
  data,
  game,
  seed,
  left,
  right,
  showProbabilities,
  hideResult,
}: {
  index: ArenaIndex
  data: VersusData
  game: VersusGame
  seed: number
  left: Replay
  right: Replay
  showProbabilities: boolean
  hideResult: boolean
}) {
  const key = gameKey(game.board, game.game)
  const unit = game.unit
  const runs = useMemo(() => {
    const make = (side: Side, replay: Replay): Run => ({
      side,
      id: replay.player,
      name: playerInfo(index, replay.player).title,
      replay,
      series: seriesOf(replay, game.sync),
      positions: replay.decisions.map((d) => positionOf(d, game.sync)),
      end: data.episodes[key]?.[replay.player]?.[String(seed)]?.[2] ?? '',
      delay: data.delays[key]?.[replay.player] ?? replay.delay_steps,
    })
    return { a: make('a', left), b: make('b', right) }
  }, [index, data, key, seed, left, right, game.sync])
  const frames = useMemo(() => framesOf(runs.a.series, runs.b.series, game.sync), [runs, game.sync])
  const events = useMemo(() => matchEvents(runs.a.series, runs.b.series), [runs])
  const last = frames.at(-1) ?? 0
  const [frame, setFrame] = useState(0)
  const [wantsToPlay, setWantsToPlay] = useState(false)
  const [speed, setSpeed] = useState(() => defaultSpeed(game))
  const [next, setNext] = useState<Record<Side, boolean>>({ a: false, b: false })
  const current = Math.min(frame, Math.max(frames.length - 1, 0))
  const position = frames[current] ?? 0
  const atEnd = current >= frames.length - 1
  const playing = wantsToPlay && !atEnd

  const go = useCallback((target: number) => {
    setFrame(Math.max(0, Math.min(frames.length - 1, target)))
  }, [frames.length])
  const jump = useCallback(
    (to: number) => {
      const found = frames.findIndex((p) => p >= to)
      go(found === -1 ? frames.length - 1 : found)
    },
    [frames, go],
  )
  const eventPositions = useMemo(() => [...new Set(events.map((e) => e.position))].sort((x, y) => x - y), [events])
  const nextEvent = useCallback(() => {
    const found = eventPositions.find((p) => p > position)
    if (found !== undefined) jump(found)
  }, [eventPositions, position, jump])
  const previousEvent = useCallback(() => {
    const found = [...eventPositions].reverse().find((p) => p < position)
    jump(found ?? 0)
  }, [eventPositions, position, jump])
  const togglePlay = useCallback(() => {
    if (playing) {
      setWantsToPlay(false)
      return
    }
    if (atEnd) setFrame(0)
    setWantsToPlay(true)
  }, [playing, atEnd])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setFrame((f) => Math.min(f + 1, frames.length - 1))
    }, 1000 / speed)
    return () => {
      window.clearInterval(timer)
    }
  }, [playing, speed, frames.length])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTypingTarget(event.target)) return
      const stride = event.shiftKey ? 10 : 1
      if (event.key === 'ArrowRight') go(current + stride)
      else if (event.key === 'ArrowLeft') go(current - stride)
      else if (event.key === 'Home') go(0)
      else if (event.key === 'End') go(frames.length - 1)
      else if (event.key === ' ') togglePlay()
      else if (event.key === 'e' || event.key === 'E') nextEvent()
      else if (event.key === 'q' || event.key === 'Q') previousEvent()
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [current, go, togglePlay, frames.length, nextEvent, previousEvent])

  const views: Record<Side, SideView> = {
    a: sideAt(runs.a.replay, runs.a.positions, runs.a.series, position),
    b: sideAt(runs.b.replay, runs.b.positions, runs.b.series, position),
  }
  const sa = scoreAt(runs.a.series, position)
  const sb = scoreAt(runs.b.series, position)
  const names = { a: runs.a.name, b: runs.b.name }
  const gameTitle = index.games[game.game]?.title ?? game.game
  const boardTitle = index.boards.find((b) => b.id === game.board)?.title ?? game.board
  const window_ = game.board === 'macro' ? (game.game === 'tetris' ? 3 : 6) : 60
  const caption = captionAt(events, position, window_, { game: game.game, unit, names, ends: { a: runs.a.end, b: runs.b.end } })
  const paths = diffPaths(runs.a.series, runs.b.series, last, position)
  const callout = stateCallout(events, position, game.game, runs, sa, sb)
  const chase = events.find((e) => e.kind === 'chase')
  const par = data.par[key]?.[String(seed)]
  const rows = seedRows(data, game.board, game.game, runs.a.id, runs.b.id)
  const series = seriesRecord(rows)
  const lead = sa === sb ? null : sa > sb ? 'a' : 'b'
  const scoreName = index.games[game.game]?.score ?? 'score'

  const snapA = record(views.a.snapshot)
  const snapB = record(views.b.snapshot)
  const pieceA = record(snapA.piece).kind
  const pieceB = record(snapB.piece).kind
  const shared =
    game.game === 'tetris' && !views.a.ended && !views.b.ended && typeof pieceA === 'string' && pieceA === pieceB
      ? `${pieceA} now · ${typeof snapA.next === 'string' ? snapA.next : ''} next`
      : null

  const style = { a: styleOf(runs.a.replay.decisions, views.a.index + (views.a.ended ? 0 : 1)), b: styleOf(runs.b.replay.decisions, views.b.index + (views.b.ended ? 0 : 1)) }

  const tetrisTrend = useMemo(() => {
    if (game.game !== 'tetris') return null
    const stacks = (run: Run) => run.replay.decisions.map((d) => tetrisStack((record(d.snapshot).board as string[] | undefined) ?? []))
    return { a: stacks(runs.a), b: stacks(runs.b) }
  }, [game.game, runs])

  const sinceFood = (run: Run) => {
    let lastChange = 0
    for (let i = 1; i < run.series.points.length; i++) {
      const [p, s] = run.series.points[i] ?? [0, 0]
      if (p > position) break
      if (s !== run.series.points[i - 1]?.[1]) lastChange = p
    }
    return Math.max(0, Math.min(position, run.series.end) - lastChange)
  }
  const safeMoves = (view: SideView) => (view.decision ? view.decision.options.filter((o) => !endsTheGame(o.text)).length : 0)

  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <a href={href.versus}>Versus</a> · <a href={href.versusPick(game.board, game.game, runs.a.id, runs.b.id)}>{names.a} vs {names.b}</a> · {boardTitle} board
      </nav>

      <section aria-label="Score" className="grid grid-cols-2 items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-surface px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        {(['a', 'b'] as const).map((side) => {
          const run = runs[side]
          const info = playerInfo(index, run.id)
          return (
            <div key={side} className={`flex min-w-0 items-center gap-2.5 ${side === 'a' ? 'order-1' : 'order-2 flex-row-reverse text-right sm:order-3'}`}>
              <TeamDot side={side} />
              <div className="min-w-0">
                <h2 className="truncate text-xl font-bold tracking-tight">
                  <a href={href.model(run.id)} className="text-fg no-underline hover:underline">{run.name}</a>
                </h2>
                <span className="block truncate font-mono text-xs text-muted">
                  {info.repository ?? run.id}
                  {game.board === 'realtime' ? ` · reacts ${run.delay} steps late` : ''}
                </span>
              </div>
            </div>
          )
        })}
        <div className="order-3 col-span-2 flex flex-col items-center gap-0.5 sm:order-2 sm:col-span-1">
          <h1 className="text-center text-xs font-semibold tracking-wide text-muted uppercase">
            {gameTitle} · {boardTitle} · seed {seed} · {scoreName}
          </h1>
          <div className="flex items-baseline gap-3 font-mono text-4xl leading-none font-bold tabular-nums">
            <span className={TEAM.a.text}>{formatScore(game.game, sa)}</span>
            <span className="text-xl text-faint">:</span>
            <span className={TEAM.b.text}>{formatScore(game.game, sb)}</span>
          </div>
          {lead ? (
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-extrabold text-[#0c1113] ${TEAM[lead].fill}`}>
              {names[lead]} +{Math.abs(sa - sb)}
            </span>
          ) : (
            <span className="rounded-full border border-faint px-2.5 py-0.5 text-xs font-bold">Level</span>
          )}
          {hideResult ? null : (
            <span className="text-[11px] text-muted">
              final {formatScore(game.game, runs.a.series.final)} : {formatScore(game.game, runs.b.series.final)}
            </span>
          )}
        </div>
      </section>

      <div className="flex flex-wrap justify-center gap-1.5">
        <Badge strong>Same seed · same harness · same option order</Badge>
        <Badge>Kept in step by {game.sync === 'step' ? 'game step' : unit}</Badge>
        {par !== undefined ? <Badge>Par for this seed: {formatScore(game.game, par)} (reference)</Badge> : null}
        {game.board === 'realtime' ? <Badge>Time counts here: each model acts on a picture its delay old</Badge> : null}
      </div>

      <div className="flex flex-wrap items-start justify-center gap-4">
        {(['a', 'b'] as const).map((side) => (
          <SidePanel
            key={`panel-${side}`}
            run={runs[side]}
            view={views[side]}
            score={side === 'a' ? sa : sb}
            game={game}
            unit={unit}
            other={runs[side === 'a' ? 'b' : 'a']}
            chased={chase?.side === (side === 'a' ? 'b' : 'a')}
            showProbabilities={showProbabilities}
            next={next[side]}
            onNext={(value) => {
              setNext((n) => ({ ...n, [side]: value }))
            }}
          />
        ))}
        {(['a', 'b'] as const).map((side) => (
          <Board key={`board-${side}`} run={runs[side]} view={views[side]} game={game} showProbabilities={showProbabilities} />
        ))}
        <section aria-label="Comparison" className="order-3 flex min-w-64 flex-[0_1_18rem] flex-col gap-2.5 rounded-2xl border border-line bg-surface p-3.5">
          <h2 className="flex justify-between text-xs font-semibold text-muted">
            <span>{position >= last ? 'End of the match' : capital(currentLabel(unit, position))}</span>
            <span>{shared ?? `of ${countsFromOne(unit) ? last : `${last} ${unit}s`}`}</span>
          </h2>
          <div className={`flex flex-col gap-0.5 rounded-xl border px-3 py-2 ${callout.side ? `${TEAM[callout.side].soft} ${TEAM[callout.side].border}` : 'border-line bg-surface-2'}`}>
            <span className={`text-xs font-bold tracking-wide uppercase ${callout.side ? TEAM[callout.side].text : 'text-muted'}`}>{callout.kind}</span>
            <span className="text-base font-bold">{callout.headline}</span>
            <span className="text-xs text-muted">{callout.note}</span>
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-xs text-muted">More is better</span>
            {game.game === 'tetris' ? (
              <>
                <MirrorRow label="lines" a={sa} b={sb} />
                <MirrorRow label="pieces placed" a={Number(snapA.pieces ?? 0)} b={Number(snapB.pieces ?? 0)} />
              </>
            ) : null}
            {game.game === 'snake' ? (
              <>
                <MirrorRow label="food" a={sa} b={sb} />
                <MirrorRow label="length" a={Array.isArray(snapA.snake) ? snapA.snake.length : 0} b={Array.isArray(snapB.snake) ? snapB.snake.length : 0} />
                <MirrorRow label="safe moves of 3" a={safeMoves(views.a)} b={safeMoves(views.b)} />
              </>
            ) : null}
            {game.game === 'pong' ? (
              <MirrorRow
                label="points won"
                a={Array.isArray(snapA.score) ? Number((snapA.score as number[])[0]) : 0}
                b={Array.isArray(snapB.score) ? Number((snapB.score as number[])[0]) : 0}
              />
            ) : null}
            {game.game === 'breakout' ? (
              <>
                <MirrorRow label="score" a={sa} b={sb} />
                <MirrorRow label="lives" a={Number(snapA.lives ?? 0)} b={Number(snapB.lives ?? 0)} />
                <MirrorRow label="bricks broken" a={bricksBroken(snapA)} b={bricksBroken(snapB)} />
              </>
            ) : null}
          </div>
          {game.game === 'breakout' ? null : (
            <div className="flex flex-col gap-2 border-t border-line pt-2.5">
              <span className="text-xs text-muted">Less is better</span>
              {game.game === 'tetris' && tetrisTrend ? (
                <>
                  <LowerRow
                    label="stack height"
                    a={(tetrisTrend.a[Math.min(views.a.index, tetrisTrend.a.length - 1)] ?? { height: 0 }).height}
                    b={(tetrisTrend.b[Math.min(views.b.index, tetrisTrend.b.length - 1)] ?? { height: 0 }).height}
                    trend={{ a: tetrisTrend.a.slice(0, views.a.index + 1).map((s) => s.height), b: tetrisTrend.b.slice(0, views.b.index + 1).map((s) => s.height), last, top: 20 }}
                  />
                  <LowerRow
                    label="holes"
                    a={(tetrisTrend.a[Math.min(views.a.index, tetrisTrend.a.length - 1)] ?? { holes: 0 }).holes}
                    b={(tetrisTrend.b[Math.min(views.b.index, tetrisTrend.b.length - 1)] ?? { holes: 0 }).holes}
                    trend={{
                      a: tetrisTrend.a.slice(0, views.a.index + 1).map((s) => s.holes),
                      b: tetrisTrend.b.slice(0, views.b.index + 1).map((s) => s.holes),
                      last,
                      top: Math.max(8, ...tetrisTrend.a.map((s) => s.holes), ...tetrisTrend.b.map((s) => s.holes)),
                    }}
                  />
                </>
              ) : null}
              {game.game === 'snake' ? <LowerRow label={`${unit}s since the last food`} a={sinceFood(runs.a)} b={sinceFood(runs.b)} /> : null}
              {game.game === 'pong' ? (
                <LowerRow
                  label="points conceded"
                  a={Array.isArray(snapA.score) ? Number((snapA.score as number[])[1]) : 0}
                  b={Array.isArray(snapB.score) ? Number((snapB.score as number[])[1]) : 0}
                />
              ) : null}
            </div>
          )}
          <details className="border-t border-line pt-1.5">
            <summary className="py-1.5 text-sm font-semibold text-muted">Decision style and time</summary>
            <dl className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Mean choice probability</dt>
              <dd className={`text-right ${TEAM.a.text}`}>{percent(style.a.meanChoice)}</dd>
              <dd className={`text-right ${TEAM.b.text}`}>{percent(style.b.meanChoice)}</dd>
              <dt className="text-muted">Close calls (top two within 5 points)</dt>
              <dd className={`text-right ${TEAM.a.text}`}>{percent(style.a.closeShare)}</dd>
              <dd className={`text-right ${TEAM.b.text}`}>{percent(style.b.closeShare)}</dd>
              <dt className="text-muted">Per request, median / p95</dt>
              <dd className={`text-right ${TEAM.a.text}`}>
                {Math.round(style.a.median ?? 0)} / {Math.round(style.a.p95 ?? 0)} ms
              </dd>
              <dd className={`text-right ${TEAM.b.text}`}>
                {Math.round(style.b.median ?? 0)} / {Math.round(style.b.p95 ?? 0)} ms
              </dd>
              <dt className="text-muted">Requests so far</dt>
              <dd className={`text-right ${TEAM.a.text}`}>{style.a.requests}</dd>
              <dd className={`text-right ${TEAM.b.text}`}>{style.b.requests}</dd>
            </dl>
            <p className="mt-1.5 text-xs text-muted">
              {game.board === 'realtime'
                ? 'On the real-time board time decides how late each choice lands; the delay was measured before the run.'
                : 'Time does not count on this board: the game waits for every answer.'}
            </p>
          </details>
          <span className="text-xs text-muted">
            Series on {gameTitle}, {boardTitle.toLowerCase()} board, {rows.length} seeds: {names.a} {series.wins}, {names.b} {series.losses}, {series.draws} drawn
          </span>
        </section>
      </div>

      <CaptionBox caption={caption} />

      <section aria-label="Timeline" className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface px-4 py-3">
        <Timeline paths={paths} last={last} position={position} events={events} names={names} onJump={jump} />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="flex gap-1.5">
            <button type="button" aria-label="Previous event" onClick={previousEvent} className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2 text-fg">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6l-8 6 8 6" />
                <path d="M6 5v14" />
              </svg>
            </button>
            <button type="button" aria-label="One back" onClick={() => { go(current - 1) }} className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2 text-fg">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 6l-6 6 6 6" />
              </svg>
            </button>
            <button
              type="button"
              onClick={togglePlay}
              className="inline-flex h-10 min-w-20 items-center justify-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-bold text-white dark:text-[var(--bg)]"
            >
              {playing ? 'Pause' : atEnd ? 'Replay' : 'Play'}
            </button>
            <button type="button" aria-label="One forward" onClick={() => { go(current + 1) }} className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2 text-fg">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
            <button type="button" aria-label="Next event" onClick={nextEvent} className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2 text-fg">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 6l8 6-8 6" />
                <path d="M18 5v14" />
              </svg>
            </button>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            Speed
            <select
              value={speed}
              onChange={(event) => {
                setSpeed(Number(event.target.value))
              }}
              className="h-9 rounded-md border border-line bg-surface px-1.5 text-xs text-fg"
            >
              {SPEEDS.map((value) => (
                <option key={value} value={value}>
                  {value} / s
                </option>
              ))}
            </select>
          </label>
          <input
            type="range"
            min={0}
            max={Math.max(frames.length - 1, 0)}
            value={current}
            onChange={(event) => {
              go(Number(event.target.value))
            }}
            aria-label={capital(unit)}
            aria-valuetext={currentLabel(unit, position)}
            className="min-w-40 flex-1 accent-[var(--accent)]"
          />
          <span className="font-mono text-xs text-muted tabular-nums">{position >= last ? 'end' : currentLabel(unit, position)}</span>
        </div>
        <nav aria-label="Events" className="flex flex-wrap gap-1.5">
          {shownEvents(events)
            .filter((e) => e.position <= position)
            .map((event, i) => (
              <button
                key={`${event.kind}-${event.position}-${i}`}
                type="button"
                onClick={() => {
                  jump(event.position)
                }}
                className={`rounded-full border px-2.5 py-1 text-xs ${event.position === position ? 'border-accent bg-accent-soft font-bold text-accent-strong' : 'border-line text-muted'}`}
              >
                {eventLabel(event, names, unit)}
              </button>
            ))}
        </nav>
        <p className="text-xs text-muted">Keys: E next event · Q previous event · ← → one {unit} (Shift: 10) · Space play</p>
      </section>
    </div>
  )
}
