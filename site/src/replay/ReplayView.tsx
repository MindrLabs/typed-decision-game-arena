import { useCallback, useEffect, useState } from 'react'

import { formatCompact, formatValue, metricLabel } from '../lib/format'
import { playerInfo } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, Replay } from '../lib/types'
import { DecisionPanel, FinalPanel } from './DecisionPanel'
import { GameCanvas } from './GameCanvas'
import { bandOf, describeSnapshot, isConnect4, landingOf } from './renderers'

const SPEEDS = [1, 2, 5, 10, 20, 50] as const

export function defaultSpeed(replay: Pick<Replay, 'board' | 'game'>): number {
  if (replay.board !== 'macro') return 20
  if (replay.game === 'connect4') return 1
  if (replay.game === 'snake') return 10
  return 5
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'SUMMARY', 'A'].includes(target.tagName) || target.isContentEditable
}

function Swatch({ colour, label }: { colour: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span aria-hidden="true" className="inline-block size-2.5 rounded-full" style={{ background: colour }} />
      {label}
    </span>
  )
}

/** Which colour is whom, where the picture alone does not say. */
function Legend({ game, snapshot }: { game: string; snapshot: unknown }) {
  if (game === 'connect4' && isConnect4(snapshot)) {
    return (
      <p className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-muted">
        <Swatch colour="var(--game-x)" label={`X moves first${snapshot.you === 'X' ? ' (player)' : ` (${snapshot.opponent})`}`} />
        <Swatch colour="var(--game-o)" label={`O${snapshot.you === 'O' ? ' (player)' : ` (${snapshot.opponent})`}`} />
      </p>
    )
  }
  if (game === 'pong') {
    return (
      <p className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-muted">
        <Swatch colour="var(--game-player)" label="player (right)" />
        <Swatch colour="var(--game-opponent)" label="built-in opponent (left)" />
      </p>
    )
  }
  return null
}

function ControlButton({ label, onClick, children, disabled }: { label: string; onClick: () => void; children: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-8 min-w-8 items-center justify-center rounded-md border border-line bg-surface px-2 text-sm text-fg transition-colors hover:bg-surface-2 disabled:opacity-40"
    >
      {children}
    </button>
  )
}

export function ReplayView({ index, replay }: { index: ArenaIndex; replay: Replay }) {
  const final = replay.final ?? null
  const total = replay.decisions.length
  // One frame per decision, plus the position after the last move when the export has it.
  const frames = total + (final ? 1 : 0)
  const [position, setPosition] = useState(0)
  const [wantsToPlay, setWantsToPlay] = useState(false)
  const [speed, setSpeed] = useState(() => defaultSpeed(replay))
  const [hover, setHover] = useState<{ frame: number; key: string } | null>(null)
  const current = Math.min(position, Math.max(frames - 1, 0))
  const atEnd = current >= frames - 1
  const playing = wantsToPlay && !atEnd

  const go = useCallback(
    (next: number) => {
      setPosition(Math.max(0, Math.min(frames - 1, next)))
    },
    [frames],
  )

  const togglePlay = useCallback(() => {
    if (playing) {
      setWantsToPlay(false)
      return
    }
    if (atEnd) setPosition(0)
    setWantsToPlay(true)
  }, [playing, atEnd])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setPosition((p) => Math.min(p + 1, frames - 1))
    }, 1000 / speed)
    return () => {
      window.clearInterval(timer)
    }
  }, [playing, speed, frames])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTypingTarget(event.target)) return
      const stride = event.shiftKey ? 10 : 1
      if (event.key === 'ArrowRight') go(current + stride)
      else if (event.key === 'ArrowLeft') go(current - stride)
      else if (event.key === 'Home') go(0)
      else if (event.key === 'End') go(frames - 1)
      else if (event.key === ' ') togglePlay()
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [current, go, togglePlay, frames])

  const player = playerInfo(index, replay.player)
  const gameTitle = index.games[replay.game]?.title ?? replay.game
  const boardTitle = index.boards.find((board) => board.id === replay.board)?.title ?? replay.board
  const metrics = Object.entries(replay.metrics)

  const isFinal = final !== null && current === total
  const decision = isFinal ? undefined : replay.decisions[current]
  const snapshot = isFinal ? final.snapshot : decision?.snapshot
  const step = isFinal ? final.step : decision?.step
  const status = snapshot === undefined ? '' : describeSnapshot(replay.game, snapshot)
  const macro = replay.board === 'macro'
  const band = macro && decision ? bandOf(replay.game, decision.choice) : undefined
  const ghost = macro && decision ? landingOf(snapshot, decision.choice) : undefined
  const preview = decision && hover?.frame === current ? landingOf(snapshot, hover.key) : undefined
  const frameLabel = isFinal ? 'end of game' : `decision ${current + 1} / ${total}`
  const onHoverOption = ghost
    ? (key: string | null) => {
        setHover(key === null ? null : { frame: current, key })
      }
    : undefined

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <nav aria-label="Breadcrumb" className="text-xs text-muted">
          <a href={href.board(replay.board)}>{boardTitle} board</a> · <a href={href.model(replay.player)}>{player.title}</a>
        </nav>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {gameTitle} <span className="font-normal text-muted">· {player.title} · seed {replay.seed}</span>
        </h1>
        <p className="text-sm text-muted">
          Final score <span className="font-mono text-fg">{formatCompact(replay.score)}</span>
          {replay.delay_steps > 0 ? ` · reaction delay ${replay.delay_steps} steps` : ''}
          {metrics.length > 0 ? ' · ' : ''}
          {metrics.map(([name, value], i) => (
            <span key={name}>
              {i > 0 ? ', ' : ''}
              {metricLabel(name)} <span className="font-mono text-fg">{formatValue(value)}</span>
            </span>
          ))}
        </p>
      </div>

      {snapshot !== undefined && step !== undefined ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
          <div className="flex min-w-0 flex-col gap-3">
            <div className="rounded-xl border border-line bg-surface p-3">
              <GameCanvas
                game={replay.game}
                snapshot={snapshot}
                label={`${gameTitle}, ${frameLabel}: ${status}`}
                band={band}
                ghost={ghost}
                preview={preview}
              />
              <p className="mt-2 text-center font-mono text-xs text-muted" aria-live="polite">
                {isFinal ? `end of game: ${status}` : status}
              </p>
              <Legend game={replay.game} snapshot={snapshot} />
              {band ? <p className="mt-1 text-center text-[11px] text-faint">The shaded strip is the band this decision chose.</p> : null}
              {ghost ? (
                <p className="mt-1 text-center text-[11px] text-faint">
                  The outlined cells are where the chosen placement lands; point at an option to compare.
                </p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <ControlButton label="First decision" onClick={() => { go(0) }} disabled={current === 0}>
                  ⏮
                </ControlButton>
                <ControlButton label="Previous" onClick={() => { go(current - 1) }} disabled={current === 0}>
                  ◀
                </ControlButton>
                <button
                  type="button"
                  onClick={togglePlay}
                  aria-label={playing ? 'Pause' : 'Play'}
                  className="inline-flex h-8 min-w-16 items-center justify-center rounded-md bg-accent px-3 text-sm font-medium text-white dark:text-[var(--bg)]"
                >
                  {playing ? 'Pause' : atEnd ? 'Replay' : 'Play'}
                </button>
                <ControlButton label="Next" onClick={() => { go(current + 1) }} disabled={atEnd}>
                  ▶
                </ControlButton>
                <ControlButton label={final ? 'End of game' : 'Last decision'} onClick={() => { go(frames - 1) }} disabled={atEnd}>
                  ⏭
                </ControlButton>
                <label className="ml-auto flex items-center gap-1.5 text-xs text-muted">
                  Speed
                  <select
                    value={speed}
                    onChange={(event) => {
                      setSpeed(Number(event.target.value))
                    }}
                    className="h-8 rounded-md border border-line bg-surface px-1.5 text-xs text-fg"
                  >
                    {SPEEDS.map((value) => (
                      <option key={value} value={value}>
                        {value} / s
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(frames - 1, 0)}
                value={current}
                onChange={(event) => {
                  go(Number(event.target.value))
                }}
                aria-label="Decision"
                aria-valuetext={isFinal ? `end of game, step ${step}` : `decision ${current + 1} of ${total}, step ${step}`}
                className="w-full accent-[var(--accent)]"
              />
              <div className="flex flex-wrap justify-between gap-2 font-mono text-xs tabular-nums text-muted">
                <span>{frameLabel}</span>
                <span>game step {step}</span>
              </div>
              <p className="text-[11px] text-faint">Keys: ← → step (Shift: 10), Space play/pause, Home/End.</p>
            </div>
          </div>
          <aside aria-label={isFinal ? 'End of game' : 'Decision'} className="min-w-0 rounded-xl border border-line bg-surface p-4">
            {decision ? (
              <DecisionPanel decision={decision} onHoverOption={onHoverOption} />
            ) : (
              <FinalPanel replay={replay} scoreLabel={index.games[replay.game]?.score} step={step} decisions={total} />
            )}
          </aside>
        </div>
      ) : (
        <p className="text-muted">This replay has no decisions.</p>
      )}
    </div>
  )
}
