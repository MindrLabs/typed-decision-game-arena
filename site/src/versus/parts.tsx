import type { ReactNode } from 'react'

import { formatMs } from '../lib/format'
import type { ReplayDecision } from '../lib/types'
import {
  decisionMs,
  endsTheGame,
  groupsOf,
  shownEvents,
  topOptions,
  type Caption,
  type DiffPaths,
  type MatchEvent,
  type Side,
} from '../lib/versus'

export const TEAM: Record<Side, { text: string; fill: string; soft: string; border: string; css: string }> = {
  a: { text: 'text-team-a', fill: 'bg-team-a-fill', soft: 'bg-team-a-soft', border: 'border-team-a-fill', css: 'var(--team-a-fill)' },
  b: { text: 'text-team-b', fill: 'bg-team-b-fill', soft: 'bg-team-b-soft', border: 'border-team-b-fill', css: 'var(--team-b-fill)' },
}

export function TeamDot({ side, className = 'size-3' }: { side: Side; className?: string }) {
  return <span aria-hidden="true" className={`inline-block shrink-0 rounded-full ${TEAM[side].fill} ${className}`} />
}

export function Badge({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs ${strong ? 'bg-accent-soft font-semibold text-accent-strong' : 'bg-surface-2 text-muted'}`}
    >
      {children}
    </span>
  )
}

export function percent(p: number | null | undefined): string {
  return p === null || p === undefined ? '—' : `${Math.round(p * 100)}%`
}

/** Two values from the middle outwards; the larger is coloured. For "more is better" counts only. */
export function MirrorRow({ label, a, b, format = String }: { label: string; a: number; b: number; format?: (v: number) => string }) {
  const top = Math.max(Math.abs(a), Math.abs(b)) || 1
  const width = (v: number) => `${((Math.max(v, 0) / top) * 100).toFixed(1)}%`
  return (
    <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1fr)_2.5rem] items-center gap-x-1.5">
      <span className={`text-right font-mono font-bold tabular-nums ${a > b ? TEAM.a.text : 'text-fg'}`}>{format(a)}</span>
      <span aria-hidden="true" className="flex h-2 justify-end rounded-l bg-surface-2">
        <span className={`block h-2 rounded-l ${TEAM.a.fill}`} style={{ width: width(a) }} />
      </span>
      <span aria-hidden="true" className="flex h-2 rounded-r bg-surface-2">
        <span className={`block h-2 rounded-r ${TEAM.b.fill}`} style={{ width: width(b) }} />
      </span>
      <span className={`font-mono font-bold tabular-nums ${b > a ? TEAM.b.text : 'text-fg'}`}>{format(b)}</span>
      <span className="col-span-4 -mt-0.5 text-center text-xs text-muted">{label}</span>
    </div>
  )
}

export function Sparkline({ values, last, top, side }: { values: readonly number[]; last: number; top: number; side: Side }) {
  if (values.length < 2) return <span aria-hidden="true" className="block h-7" />
  const points = values.map((v, i) => `${((i / Math.max(last, 1)) * 120).toFixed(1)},${(30 - (v / Math.max(top, 1)) * 28).toFixed(1)}`).join(' ')
  return (
    <svg aria-hidden="true" viewBox="0 0 120 32" preserveAspectRatio="none" className="block h-7 w-full">
      <polyline points={points} fill="none" stroke={TEAM[side].css} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/** A value where less is better: numbers and a small trend, never a bar. */
export function LowerRow({
  label,
  a,
  b,
  trend,
}: {
  label: string
  a: number | null
  b: number | null
  trend?: { a: readonly number[]; b: readonly number[]; last: number; top: number }
}) {
  const better = a !== null && b !== null && a !== b ? (a < b ? 'a' : 'b') : null
  return (
    <div className="grid grid-cols-[2.25rem_minmax(0,1fr)_minmax(0,1fr)_2.25rem] items-center gap-x-1.5">
      <span className={`text-right font-mono font-bold tabular-nums ${better === 'a' ? TEAM.a.text : 'text-fg'}`}>{a ?? '—'}</span>
      {trend ? <Sparkline values={trend.a} last={trend.last} top={trend.top} side="a" /> : <span />}
      {trend ? <Sparkline values={trend.b} last={trend.last} top={trend.top} side="b" /> : <span />}
      <span className={`font-mono font-bold tabular-nums ${better === 'b' ? TEAM.b.text : 'text-fg'}`}>{b ?? '—'}</span>
      <span className="col-span-4 -mt-0.5 text-center text-xs text-muted">{label}</span>
    </div>
  )
}

/** The decision a side makes at this position: the final request's options by probability, the knockout folded. */
export function DecisionCard({
  side,
  decision,
  title,
  showProbabilities,
}: {
  side: Side
  decision: ReplayDecision
  title: string
  showProbabilities: boolean
}) {
  const options = topOptions(decision)
  const groups = groupsOf(decision)
  const total = decision.options.length
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3 text-left">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">{showProbabilities ? 'Choice probability' : 'Choice'}</span>
        <span className="text-xs text-muted">{title}</span>
      </div>
      {decision.forced ? (
        <p className="text-sm">
          <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-xs">{decision.choice}</span>{' '}
          <span className="text-muted">forced: the only legal move, nothing was asked</span>
        </p>
      ) : (
        <ol className="flex flex-col gap-2">
          {options.map((option, i) => {
            const chosen = option.key === decision.choice
            const danger = endsTheGame(option.text)
            return (
              <li key={option.key} className="flex flex-col gap-1">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                      danger ? 'bg-danger text-surface' : `${TEAM[side].fill} text-[#0c1113]`
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="font-mono text-sm font-bold">{option.key}</span>
                  {chosen ? <span className="text-[11px] font-semibold text-muted">chosen</span> : null}
                  {danger ? <span className="text-[11px] font-bold text-danger">ends the game</span> : null}
                  {showProbabilities ? <span className="ml-auto font-mono text-sm font-bold tabular-nums">{percent(option.p)}</span> : null}
                </div>
                {showProbabilities && option.p !== null ? (
                  <span aria-hidden="true" className="block h-1 rounded bg-surface-2">
                    <span className={`block h-1 rounded ${i === 0 ? TEAM[side].fill : 'bg-faint'}`} style={{ width: `${(option.p * 100).toFixed(1)}%` }} />
                  </span>
                ) : null}
                {option.text ? <span className="text-xs text-muted">{option.text}</span> : null}
              </li>
            )
          })}
        </ol>
      )}
      {groups.length > 0 ? (
        <details className="text-xs text-muted">
          <summary className="py-1 font-semibold">
            {total} options in {groups.length} groups, then a final of {decision.calls.at(-1)?.keys.length ?? 0}
          </summary>
          <ul className="mt-1 flex flex-col gap-0.5 font-mono">
            {groups.map((group, i) => (
              <li key={i}>
                group {i + 1} · {group.size} options → {group.choice} {percent(group.p)}
              </li>
            ))}
          </ul>
          <p className="mt-1">Group shares and final shares are on different scales.</p>
        </details>
      ) : null}
      {decision.forced ? null : (
        <span className="text-xs text-muted">
          {decision.calls.length} request{decision.calls.length === 1 ? '' : 's'} · {formatMs(decisionMs(decision))}
        </span>
      )}
    </div>
  )
}

export function CaptionBox({ caption }: { caption: Caption | null }) {
  const side = caption?.side
  return (
    <aside
      aria-label="Caption"
      aria-live="polite"
      className={`mx-auto flex min-h-[5.5rem] w-full max-w-3xl flex-col justify-center gap-0.5 rounded-xl border border-line bg-surface px-5 py-3 ${
        side ? (side === 'a' ? 'shadow-[inset_4px_0_0_var(--team-a-fill)]' : 'shadow-[inset_4px_0_0_var(--team-b-fill)]') : ''
      }`}
    >
      {caption ? (
        <>
          <span className={`text-xs font-semibold ${side ? TEAM[side].text : 'text-muted'}`}>{caption.header}</span>
          <span className="text-lg leading-snug font-bold">{caption.headline}</span>
          <span className="text-xs text-muted">{caption.scope}</span>
        </>
      ) : (
        <span className="text-sm text-muted">Nothing has separated the two runs here.</span>
      )}
    </aside>
  )
}

const EVENT_ICON: Record<MatchEvent['kind'], string> = { first: '↑', lead: '⇅', level: '=', end: '×', chase: '⚑' }

export function eventLabel(event: MatchEvent, names: Record<Side, string>, unit: string): string {
  const who = event.side ? names[event.side] : ''
  switch (event.kind) {
    case 'first':
      return `${unit} ${event.position} · ${who} ahead`
    case 'lead':
      return `${unit} ${event.position} · ${who} ahead`
    case 'level':
      return `${unit} ${event.position} · level`
    case 'end':
      return `${unit} ${event.position} · ${who} out`
    case 'chase':
      return `${unit} ${event.position} · ${who} chases`
  }
}

export function Timeline({
  paths,
  last,
  position,
  events,
  names,
  onJump,
}: {
  paths: DiffPaths
  last: number
  position: number
  events: readonly MatchEvent[]
  names: Record<Side, string>
  onJump: (position: number) => void
}) {
  const x = (p: number) => (last > 0 ? (Math.min(p, last) / last) * 100 : 0)
  const shown = shownEvents(events).filter((e) => e.position <= position)
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap justify-between gap-x-3 text-xs text-muted">
        <span>
          <span className={TEAM.a.text}>Above the line: {names.a} ahead</span> · <span className={TEAM.b.text}>below: {names.b} ahead</span>
        </span>
        <span>Drawn up to the current position only</span>
      </div>
      <div className="relative">
        <svg
          role="img"
          aria-label={`Score difference up to the current position; ${shown.length} events so far`}
          viewBox="0 0 1000 120"
          preserveAspectRatio="none"
          className="block h-28 w-full rounded-lg bg-surface-2"
        >
          <line x1="0" x2="1000" y1="60" y2="60" stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          <path d={paths.above} fill="var(--team-a-fill)" fillOpacity="0.5" stroke="var(--team-a-fill)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          <path d={paths.below} fill="var(--team-b-fill)" fillOpacity="0.5" stroke="var(--team-b-fill)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          <line x1={x(position) * 10} x2={x(position) * 10} y1="0" y2="120" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </svg>
        {shown.map((event, i) => {
          const tone = event.side ? TEAM[event.side] : null
          const top = event.side === 'a' ? 'top-1' : event.side === 'b' ? 'bottom-1' : 'top-1/2 -translate-y-1/2'
          return (
            <button
              key={`${event.kind}-${event.position}-${i}`}
              type="button"
              title={eventLabel(event, names, 'at')}
              aria-label={eventLabel(event, names, 'jump to')}
              onClick={() => {
                onJump(event.position)
              }}
              className={`absolute ${top} inline-flex h-6 min-w-6 -translate-x-1/2 items-center justify-center rounded-full border-2 bg-surface px-1 text-[11px] font-extrabold ${
                tone ? `${tone.border} ${tone.text}` : 'border-faint text-muted'
              }`}
              style={{ left: `${x(event.position)}%` }}
            >
              {EVENT_ICON[event.kind]}
            </button>
          )
        })}
      </div>
    </div>
  )
}
