import { Suspense, use, useCallback, useEffect, useMemo, useState } from 'react'

import { ErrorBoundary } from '../components/ErrorBoundary'
import { duelPath, duelResource, versusResource } from '../lib/data'
import { formatMs, formatNumber } from '../lib/format'
import { playerInfo } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, DuelDecision, DuelReplay, DuelSnapshot, VersusData } from '../lib/types'
import { pairId, topOptions, type Side } from '../lib/versus'
import { Missing } from './MatchPage'
import { Badge, TEAM, TeamDot, percent } from './parts'

const WINS = 'wins the game'
const GIVES = 'the opponent can complete four'
const BLOCKS = 'takes the cell where the opponent could complete four'

type DuelEventKind = 'threat' | 'missed' | 'allowed' | 'win' | 'draw'

interface DuelEvent {
  move: number
  kind: DuelEventKind
  side: Side
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'SUMMARY', 'A'].includes(target.tagName) || target.isContentEditable
}

/** Engine facts in the option texts tell threats, missed wins and allowed wins apart without a solver. */
function duelEvents(replay: DuelReplay, sideOf: (player: string) => Side): DuelEvent[] {
  const events: DuelEvent[] = []
  for (const d of replay.decisions) {
    const side = sideOf(d.player)
    const texts = new Map(d.options.map((o) => [o.key, o.text]))
    const chosen = texts.get(d.choice) ?? ''
    if (d.options.some((o) => o.text.includes(BLOCKS))) events.push({ move: d.step, kind: 'threat', side: side === 'a' ? 'b' : 'a' })
    if (d.options.some((o) => o.text.includes(WINS)) && !chosen.includes(WINS)) events.push({ move: d.step, kind: 'missed', side })
    if (chosen.includes(GIVES) && d.options.some((o) => !o.text.includes(GIVES))) events.push({ move: d.step, kind: 'allowed', side })
  }
  const final = replay.final
  if (final) {
    const s = final.snapshot as DuelSnapshot
    if (replay.result === 'draw') events.push({ move: s.moves, kind: 'draw', side: 'a' })
    else events.push({ move: s.moves, kind: 'win', side: sideOf(replay.result === 'X' ? replay.x : replay.o) })
  }
  return events
}

function counts(events: readonly DuelEvent[], move: number, side: Side, kind: DuelEventKind): number {
  return events.filter((e) => e.kind === kind && e.side === side && e.move < move).length
}

function DuelView({ index, data, replay, a, b }: { index: ArenaIndex; data: VersusData; replay: DuelReplay; a: string; b: string }) {
  const ids: Record<Side, string> = { a, b }
  const names = { a: playerInfo(index, a).title, b: playerInfo(index, b).title }
  const sideOf = useCallback((player: string): Side => (player === a ? 'a' : 'b'), [a])
  const xSide = sideOf(replay.x)
  const decisions = replay.decisions
  const frames = decisions.length + (replay.final ? 1 : 0)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const current = Math.min(frame, frames - 1)
  const decision: DuelDecision | undefined = decisions[current]
  const snapshot = (decision ? decision.snapshot : replay.final?.snapshot) as DuelSnapshot | undefined
  const move = snapshot?.moves ?? 0
  const events = useMemo(() => duelEvents(replay, sideOf), [replay, sideOf])
  const toMove: Side | null = decision ? sideOf(decision.player) : null
  const atEnd = current >= frames - 1

  const go = useCallback((target: number) => {
    setFrame(Math.max(0, Math.min(frames - 1, target)))
  }, [frames])
  useEffect(() => {
    if (!playing || atEnd) return
    const timer = window.setInterval(() => {
      setFrame((f) => Math.min(f + 1, frames - 1))
    }, 900)
    return () => {
      window.clearInterval(timer)
    }
  }, [playing, atEnd, frames])
  const eventFrames = useMemo(() => [...new Set(events.map((e) => Math.max(0, decisions.findIndex((d) => d.step >= e.move))))].sort((x, y) => x - y), [events, decisions])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTypingTarget(event.target)) return
      if (event.key === 'ArrowRight') go(current + 1)
      else if (event.key === 'ArrowLeft') go(current - 1)
      else if (event.key === ' ') setPlaying((p) => !p)
      else if (event.key === 'e' || event.key === 'E') go(eventFrames.find((f) => f > current) ?? frames - 1)
      else if (event.key === 'q' || event.key === 'Q') go([...eventFrames].reverse().find((f) => f < current) ?? 0)
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [current, go, eventFrames, frames])

  const pair = pairId(a, b)
  const openingPoints = data.duel?.pairs[pair]?.openings[String(replay.seed)] ?? {}
  const otherGame = replay.game_no === 1 ? 2 : 1
  const otherRow = data.duel?.games[pair]?.find((g) => g.seed === replay.seed && g.game_no === otherGame)
  const options = decision ? topOptions(decision, 7) : []
  const pByColumn = new Map(options.map((o) => [o.key, o.p]))
  const blockColumn = decision?.options.find((o) => o.text.includes(BLOCKS))?.key
  const grid = snapshot?.grid ?? []
  const lastRow = snapshot?.last ? grid.findIndex((line) => line[(snapshot.last ?? 1) - 1] !== '.') : -1
  const blockText = decision?.options.find((o) => o.key === blockColumn)?.text ?? ''
  const threatRow = blockColumn ? 6 - Number(/row (\d+)/.exec(blockText)?.[1] ?? 0) : -1
  const discSide = (mark: string): Side | null => (mark === 'X' ? xSide : mark === 'O' ? (xSide === 'a' ? 'b' : 'a') : null)
  const latest = [...events].reverse().find((e) => e.move <= move)
  const captionFor = (e: DuelEvent | undefined) => {
    if (!e) return null
    const who = names[e.side]
    const other = names[e.side === 'a' ? 'b' : 'a']
    switch (e.kind) {
      case 'threat':
        return { side: e.side, headline: `${who} threatens four. ${other} has one column to stop it.`, scope: 'The other options each leave a four on the next move.' }
      case 'missed':
        return { side: e.side, headline: `${who} misses a winning move.`, scope: 'A column that completed four was on offer.' }
      case 'allowed':
        return { side: e.side, headline: `${who} leaves ${other} a four.`, scope: 'Another column did not.' }
      case 'win':
        return { side: e.side, headline: `${who} completes four and wins.`, scope: `Game ${replay.game_no} of the pair.` }
      case 'draw':
        return { side: null, headline: 'The board is full: a draw.', scope: `Game ${replay.game_no} of the pair.` }
    }
  }
  const caption = captionFor(latest)
  const result = replay.result === 'draw' ? 'draw' : `${names[sideOf(replay.result === 'X' ? replay.x : replay.o)]} won`

  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <a href={href.versus}>Versus</a> · <a href={href.versusPick('direct', 'connect4', a, b)}>{names.a} vs {names.b}</a> · Connect Four
      </nav>
      <section aria-label="Pair score" className="grid grid-cols-2 items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-surface px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        {(['a', 'b'] as const).map((side) => (
          <div key={side} className={`flex min-w-0 items-center gap-2.5 ${side === 'a' ? 'order-1' : 'order-2 flex-row-reverse text-right sm:order-3'}`}>
            <TeamDot side={side} className="size-3.5" />
            <div className="min-w-0">
              <h2 className="truncate text-xl font-bold tracking-tight">{names[side]}</h2>
              <span className="text-xs text-muted">{replay.x === ids[side] ? 'X, moves first in this game' : 'O in this game'}</span>
            </div>
          </div>
        ))}
        <div className="order-3 col-span-2 flex flex-col items-center sm:order-2 sm:col-span-1">
          <h1 className="text-center text-xs font-semibold tracking-wide text-muted uppercase">Connect Four · opening {replay.seed} · game pair</h1>
          <div className="flex items-baseline gap-3 font-mono text-3xl font-bold tabular-nums">
            <span className={TEAM.a.text}>{formatNumber(openingPoints[a] ?? 0, 1)}</span>
            <span className="text-lg text-faint">:</span>
            <span className={TEAM.b.text}>{formatNumber(openingPoints[b] ?? 0, 1)}</span>
          </div>
          <span className="text-[11px] text-muted">win 1, draw ½ over both games of this opening</span>
        </div>
      </section>

      <div role="group" aria-label="Game in the pair" className="flex flex-wrap justify-center gap-1.5">
        {[1, 2].map((gameNo) => {
          const active = gameNo === replay.game_no
          const xId = gameNo === replay.game_no ? replay.x : replay.o
          return (
            <a
              key={gameNo}
              href={href.duel(a, b, replay.seed, gameNo)}
              aria-current={active ? 'page' : undefined}
              className={`inline-flex min-h-10 items-center rounded-full border px-4 text-sm no-underline ${active ? 'border-accent bg-accent-soft font-bold text-accent-strong' : 'border-line text-muted'}`}
            >
              Game {gameNo} · {playerInfo(index, xId).title} moves first{gameNo !== replay.game_no && !otherRow ? ' · not played' : ''}
            </a>
          )
        })}
        <Badge>Opening: X c{replay.opening[0]}, O c{replay.opening[1]}</Badge>
      </div>

      <div className="flex flex-wrap items-start justify-center gap-4">
        {(['a', 'b'] as const).map((side) => {
          const own = decisions.filter((d) => sideOf(d.player) === side && d.step <= move)
          const shown = toMove === side ? decision : own.at(-1)
          const isNow = toMove === side
          return (
            <section key={side} aria-label={names[side]} className={`flex min-w-0 max-w-80 flex-1 basis-64 flex-col gap-2.5 ${side === 'a' ? 'order-1' : 'order-3'}`}>
              <div className={`flex items-center justify-between gap-2 ${side === 'b' ? 'flex-row-reverse' : ''}`}>
                <span className="inline-flex items-center gap-2 font-semibold">
                  <TeamDot side={side} className="size-4" />
                  {names[side]} · {replay.x === ids[side] ? 'X' : 'O'}
                </span>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${isNow ? `${TEAM[side].fill} text-[#0c1113]` : 'border border-faint text-muted'}`}>
                  {decision ? (isNow ? 'To move' : 'Waiting') : result}
                </span>
              </div>
              {shown ? (
                <div className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface p-3">
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="font-semibold">{isNow ? 'Choice probability' : 'Last decision'}</span>
                    <span className="text-xs text-muted">move {shown.step + 1}</span>
                  </div>
                  {(isNow ? topOptions(shown, 7) : topOptions(shown, 2)).map((o) => {
                    const block = o.text.includes(BLOCKS)
                    const gives = o.text.includes(GIVES)
                    const wins = o.text.includes(WINS)
                    return (
                      <div
                        key={o.key}
                        className={`grid grid-cols-[1.75rem_1fr_auto] items-center gap-2 rounded-md px-1.5 py-1 text-xs ${o.key === shown.choice ? `${TEAM[side].soft} font-semibold` : ''}`}
                      >
                        <span className="font-mono text-sm font-bold">{o.key}</span>
                        <span className={wins ? 'font-bold text-good' : block ? 'font-semibold' : gives ? 'text-danger' : 'text-muted'}>
                          {wins ? '★ ' : gives ? '! ' : ''}
                          {o.text.replace(/^column \d+, the disc lands in /, '')}
                        </span>
                        <span className="font-mono font-bold tabular-nums">{percent(o.p)}</span>
                      </div>
                    )
                  })}
                  <span className="text-xs text-muted">
                    {shown.calls.length} request · {formatMs(shown.calls.reduce((t, c) => t + c.ms, 0))}
                  </span>
                </div>
              ) : null}
              <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-xs">
                <dt className="text-muted">Missed wins so far</dt>
                <dd className="text-right font-mono">{counts(events, move, side, 'missed')}</dd>
                <dt className="text-muted">Allowed wins so far</dt>
                <dd className="text-right font-mono">{counts(events, move, side, 'allowed')}</dd>
              </dl>
            </section>
          )
        })}

        <div className="order-2 flex flex-col items-center gap-2">
          <div aria-hidden="true" className="grid grid-cols-7 gap-2 px-3 text-center">
            {Array.from({ length: 7 }, (_, c) => {
              const p = pByColumn.get(`c${c + 1}`)
              const top = options[0]?.key === `c${c + 1}`
              return (
                <span key={c} className={`w-12 rounded-md border py-0.5 font-mono text-xs font-bold ${top && toMove ? `${TEAM[toMove].border} ${TEAM[toMove].text}` : 'border-line text-muted'}`}>
                  {p === undefined || p === null ? '·' : percent(p)}
                </span>
              )
            })}
          </div>
          <div
            role="img"
            aria-label={`Move ${move + 1}; ${toMove ? `${names[toMove]} to move` : result}`}
            className="grid grid-cols-7 gap-2 rounded-2xl bg-[var(--game-grid)] p-3"
          >
            {grid.flatMap((line, r) =>
              line.split('').map((mark, c) => {
                const owner = discSide(mark)
                const last = snapshot?.last === c + 1 && r === lastRow
                const threat = blockColumn === `c${c + 1}` && r === threatRow
                return (
                  <span
                    key={`${r}-${c}`}
                    className={`block size-12 rounded-full ${owner ? TEAM[owner].fill : 'bg-[var(--game-bg)]'} ${last ? 'ring-3 ring-fg' : ''} ${threat ? 'border-[3px] border-dashed border-danger' : ''}`}
                  />
                )
              }),
            )}
          </div>
          <div aria-hidden="true" className="grid grid-cols-7 gap-2 px-3 text-center font-mono text-xs text-muted">
            {Array.from({ length: 7 }, (_, c) => (
              <span key={c} className="w-12">
                {c + 1}
              </span>
            ))}
          </div>
          <p className="text-center text-xs text-muted">Ringed: the last move. Dashed: the cell a side needs for four.</p>
        </div>
      </div>

      <aside
        aria-live="polite"
        className={`mx-auto flex min-h-20 w-full max-w-3xl flex-col justify-center gap-0.5 rounded-xl border border-line bg-surface px-5 py-3 ${
          caption?.side ? (caption.side === 'a' ? 'shadow-[inset_4px_0_0_var(--team-a-fill)]' : 'shadow-[inset_4px_0_0_var(--team-b-fill)]') : ''
        }`}
      >
        {caption ? (
          <>
            <span className={`text-xs font-semibold ${caption.side ? TEAM[caption.side].text : 'text-muted'}`}>
              Move {(latest?.move ?? 0) + 1}
              {caption.side ? ` · ${names[caption.side]}` : ''}
            </span>
            <span className="text-lg font-bold">{caption.headline}</span>
            <span className="text-xs text-muted">{caption.scope}</span>
          </>
        ) : (
          <span className="text-sm text-muted">Moves 1 and 2 come from the opening; the same opening is played again with the colours swapped.</span>
        )}
      </aside>

      <section aria-label="Moves" className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface px-4 py-3">
        <div className="flex flex-wrap items-end gap-1">
          {decisions.map((d, i) => {
            const side = sideOf(d.player)
            const mark = events.find((e) => e.move === d.step && e.kind !== 'win' && e.kind !== 'draw')
            return (
              <button
                key={d.i}
                type="button"
                onClick={() => {
                  go(i)
                }}
                aria-label={`Move ${d.step + 1}: ${names[side]} plays ${d.choice}`}
                className="flex w-7 flex-col items-center gap-0.5"
              >
                <span className={`h-4 text-[10px] font-extrabold ${mark ? TEAM[mark.side].text : ''}`}>{mark ? (mark.kind === 'threat' ? '!' : mark.kind === 'missed' ? 'm' : 'a') : ''}</span>
                <span className={`block size-3.5 rounded-full ${TEAM[side].fill} ${i === current ? 'ring-2 ring-accent' : i > current ? 'opacity-30' : ''}`} />
                <span className="font-mono text-[10px] text-muted">{d.step + 1}</span>
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => { go(current - 1) }} aria-label="Previous move" className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2">
            ‹
          </button>
          <button
            type="button"
            onClick={() => {
              if (atEnd) go(0)
              setPlaying((p) => !p || atEnd)
            }}
            className="h-10 min-w-20 rounded-lg bg-accent px-3 text-sm font-bold text-white dark:text-[var(--bg)]"
          >
            {playing && !atEnd ? 'Pause' : atEnd ? 'Replay' : 'Play'}
          </button>
          <button type="button" onClick={() => { go(current + 1) }} aria-label="Next move" className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface-2">
            ›
          </button>
          <span className="font-mono text-xs text-muted">{decision ? `move ${move + 1}` : `end: ${result}`}</span>
          <span className="ml-auto text-xs text-muted">Markers: ! threat · m missed win · a allowed win. Keys: E/Q events, ← → moves, Space play</span>
        </div>
      </section>
    </div>
  )
}

function LoadedDuel({ index, data, a, b, seed, gameNo }: { index: ArenaIndex; data: VersusData; a: string; b: string; seed: number; gameNo: number }) {
  const replay = use(duelResource(duelPath(pairId(a, b), seed, gameNo)))
  return <DuelView index={index} data={data} replay={replay} a={a} b={b} />
}

export function DuelPage({ index, a, b, seed, gameNo }: { index: ArenaIndex; a: string; b: string; seed: number; gameNo: number }) {
  const data = use(versusResource())
  const played = data.duel?.games[pairId(a, b)]?.some((g) => g.seed === seed && g.game_no === gameNo)
  if (a === b || !played) {
    return <Missing title="No such game">{`${a} and ${b} have no game ${gameNo} on opening ${seed} in the exported direct games.`}</Missing>
  }
  return (
    <ErrorBoundary fallback={(error) => <Missing title="The game could not be loaded">{error.message}</Missing>}>
      <Suspense
        fallback={
          <p className="text-sm text-muted" role="status">
            Loading the game…
          </p>
        }
      >
        <LoadedDuel key={`${a}/${b}/${seed}/${gameNo}`} index={index} data={data} a={a} b={b} seed={seed} gameNo={gameNo} />
      </Suspense>
    </ErrorBoundary>
  )
}
