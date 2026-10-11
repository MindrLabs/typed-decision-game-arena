/**
 * Versus logic, kept free of React: two runs of one seed compared position by position (arena/versus.py states the
 * rules; tests/golden/versus-series.json holds the cases both implementations must agree on), the events and
 * captions of a match, and the per-side numbers the match page shows.
 */
import type { Cell, ReplayDecision, Replay, SyncUnit, VersusData, VersusEpisode } from './types'

export type Side = 'a' | 'b'

export interface Series {
  /** (position, score) ascending; the first point is at 0. */
  points: [number, number][]
  /** Where the run stopped (decisions made, or the last game step). */
  end: number
  final: number
}

export interface Comparison {
  leadChanges: number
  chase: boolean
  margin: number
}

const MINUS = '−'

export function pairId(a: string, b: string): string {
  return [a, b].sort().join('~')
}

export function splitPair(pair: string): [string, string] {
  const [a = '', b = ''] = pair.split('~')
  return [a, b]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** The running score a snapshot shows, on the episode score's scale. */
export function scoreOf(game: string, snapshot: unknown): number {
  if (!isRecord(snapshot)) return 0
  switch (game) {
    case 'tetris':
      return Number(snapshot.lines ?? 0)
    case 'snake':
      return Number(snapshot.eaten ?? 0)
    case 'pong': {
      const score = snapshot.score
      return Array.isArray(score) ? Number(score[0]) - Number(score[1]) : 0
    }
    case 'breakout':
      return Number(snapshot.score ?? 0)
    default:
      return 0
  }
}

export function positionOf(decision: Pick<ReplayDecision, 'i' | 'step'>, unit: SyncUnit): number {
  return unit === 'decision' ? decision.i : decision.step
}

export function seriesOf(replay: Replay, unit: SyncUnit): Series {
  const points: [number, number][] = replay.decisions.map((d) => [positionOf(d, unit), scoreOf(replay.game, d.snapshot)])
  const final = replay.final ? scoreOf(replay.game, replay.final.snapshot) : replay.score
  const end = unit === 'decision' ? replay.decisions.length : (replay.final?.step ?? points.at(-1)?.[0] ?? 0)
  return { points: points.length > 0 ? points : [[0, final]], end, final }
}

/** The score at a position: the latest point at or before it, the final score once the run has stopped. */
export function scoreAt(series: Series, position: number): number {
  if (position >= series.end) return series.final
  let value = series.points[0]?.[1] ?? 0
  for (const [at, score] of series.points) {
    if (at > position) break
    value = score
  }
  return value
}

function positionsOf(a: Series, b: Series): number[] {
  const all = new Set<number>([a.end, b.end])
  for (const [p] of a.points) all.add(p)
  for (const [p] of b.points) all.add(p)
  return [...all].sort((x, y) => x - y)
}

export function compare(a: Series, b: Series): Comparison {
  let leader = 0
  let changes = 0
  for (const position of positionsOf(a, b)) {
    const side = Math.sign(scoreAt(a, position) - scoreAt(b, position))
    if (side !== 0 && leader !== 0 && side !== leader) changes += 1
    if (side !== 0) leader = side
  }
  const chase = (a.end < b.end && scoreAt(b, a.end) <= a.final) || (b.end < a.end && scoreAt(a, b.end) <= b.final)
  return { leadChanges: changes, chase, margin: a.final - b.final }
}

export type EventKind = 'first' | 'lead' | 'level' | 'end' | 'chase'

export interface MatchEvent {
  position: number
  kind: EventKind
  /** Who scored first, took the lead, stopped, or is chasing; null for a level score. */
  side: Side | null
  a: number
  b: number
  /** For 'lead': which change of lead this is (1, 2, ...). */
  nth?: number
  /** For 'chase': the score the survivor has to beat. */
  target?: number
}

/** The moments worth a marker: first score, every change of lead, a level score after a lead, each run's end, and a
 * chase (one run stops while the other is not ahead). */
export function matchEvents(a: Series, b: Series): MatchEvent[] {
  const events: MatchEvent[] = []
  let leader = 0
  let previous = 0
  let changes = 0
  const firstEnd = Math.min(a.end, b.end)
  for (const position of positionsOf(a, b)) {
    const sa = scoreAt(a, position)
    const sb = scoreAt(b, position)
    const sign = Math.sign(sa - sb)
    const side: Side | null = sign > 0 ? 'a' : sign < 0 ? 'b' : null
    if (sign !== 0 && leader === 0) events.push({ position, kind: 'first', side, a: sa, b: sb })
    else if (sign !== 0 && sign !== leader) {
      changes += 1
      events.push({ position, kind: 'lead', side, a: sa, b: sb, nth: changes })
    } else if (sign === 0 && previous !== 0) events.push({ position, kind: 'level', side: null, a: sa, b: sb })
    if (sign !== 0) leader = sign
    previous = sign
    for (const [who, run] of [['a', a] as const, ['b', b] as const]) {
      if (position !== run.end) continue
      events.push({ position, kind: 'end', side: who, a: sa, b: sb })
      const other = who === 'a' ? b : a
      if (position === firstEnd && run.end < other.end && scoreAt(other, position) <= run.final) {
        events.push({ position, kind: 'chase', side: who === 'a' ? 'b' : 'a', a: sa, b: sb, target: run.final })
      }
    }
  }
  return events
}

/** The events worth a chip or a marker: level scores only while the match has few other events (in long Pong and
 * Breakout games a level comes after almost every point and would bury the lead changes). */
export function shownEvents(events: readonly MatchEvent[]): MatchEvent[] {
  const others = events.filter((e) => e.kind !== 'level' && e.kind !== 'chase').length
  return events.filter((e) => e.kind !== 'chase' && (e.kind !== 'level' || others <= 6))
}

/** Every position a match steps through: each decision on the turn-based boards, the union of both runs' decision
 * steps on the real-time board. */
export function framesOf(a: Series, b: Series, unit: SyncUnit): number[] {
  const last = Math.max(a.end, b.end)
  if (unit === 'decision') return Array.from({ length: last + 1 }, (_, i) => i)
  return positionsOf(a, b)
}

/** The index of the last decision at or before `position` (binary search over ascending positions); -1 if none. */
export function lastAtOrBefore(positions: readonly number[], position: number): number {
  let low = 0
  let high = positions.length - 1
  let found = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    if ((positions[mid] ?? Infinity) <= position) {
      found = mid
      low = mid + 1
    } else high = mid - 1
  }
  return found
}

export interface SideView {
  /** The decision being made at this position; null once the run has stopped. */
  decision: ReplayDecision | null
  index: number
  snapshot: unknown
  ended: boolean
}

export function sideAt(replay: Replay, positions: readonly number[], series: Series, position: number): SideView {
  if (position >= series.end && replay.final) {
    return { decision: null, index: replay.decisions.length, snapshot: replay.final.snapshot, ended: true }
  }
  const index = Math.max(0, lastAtOrBefore(positions, position))
  const decision = replay.decisions[index] ?? null
  return { decision, index, snapshot: decision?.snapshot, ended: position >= series.end }
}

// --- per-side numbers ---------------------------------------------------------------------------------------

export interface Stack {
  height: number
  holes: number
}

/** Stack height (rows from the floor to the highest block) and holes (empty cells under a block in their column). */
export function tetrisStack(board: readonly string[]): Stack {
  const rows = board.length
  let height = 0
  let holes = 0
  const columns = board[0]?.length ?? 0
  for (let c = 0; c < columns; c++) {
    let seen = false
    for (let r = 0; r < rows; r++) {
      const filled = board[r]?.[c] === '#'
      if (filled && !seen) {
        seen = true
        height = Math.max(height, rows - r)
      } else if (!filled && seen) holes += 1
    }
  }
  return { height, holes }
}

const ENDS_GAME = /game ends|leave the grid/

export function endsTheGame(text: string): boolean {
  return ENDS_GAME.test(text)
}

/** The cell a Snake option's head enters ("row R, column C", 1-based) as a 0-based [row, column]. */
export function snakeTarget(text: string): Cell | null {
  const match = /row (\d+), column (\d+)/.exec(text)
  if (!match) return null
  return [Number(match[1]) - 1, Number(match[2]) - 1]
}

export interface RankedOption {
  key: string
  p: number | null
  text: string
}

/** The options of the final request by probability (the choice alone when the model gives no probabilities). */
export function topOptions(decision: ReplayDecision, n = 3): RankedOption[] {
  const texts = new Map(decision.options.map((o) => [o.key, o.text]))
  const final = decision.calls.at(-1)
  if (!final?.p) return [{ key: decision.choice, p: null, text: texts.get(decision.choice) ?? '' }]
  return Object.entries(final.p)
    .sort(([, x], [, y]) => y - x)
    .slice(0, n)
    .map(([key, p]) => ({ key, p, text: texts.get(key) ?? '' }))
}

export interface GroupResult {
  size: number
  choice: string
  p: number | null
}

/** The knockout groups before the final: options shown, the pick and its share within the group. */
export function groupsOf(decision: ReplayDecision): GroupResult[] {
  return decision.calls.slice(0, -1).map((call) => ({ size: call.keys.length, choice: call.choice, p: call.p?.[call.choice] ?? null }))
}

export function decisionMs(decision: ReplayDecision): number {
  return decision.calls.reduce((total, call) => total + call.ms, 0)
}

export interface Style {
  /** Mean probability of the chosen option in the final request. */
  meanChoice: number | null
  /** Share of decisions whose top two final options were within 0.05. */
  closeShare: number | null
  median: number | null
  p95: number | null
  requests: number
}

function quantile(sorted: number[], q: number): number | null {
  if (sorted.length === 0) return null
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))] ?? null
}

/** How a model decided over its first `count` decisions. */
export function styleOf(decisions: readonly ReplayDecision[], count: number): Style {
  const chosen: number[] = []
  let close = 0
  let asked = 0
  const ms: number[] = []
  for (const d of decisions.slice(0, count)) {
    for (const call of d.calls) ms.push(call.ms)
    const final = d.calls.at(-1)
    if (!final?.p) continue
    asked += 1
    chosen.push(final.p[d.choice] ?? 0)
    const values = Object.values(final.p).sort((x, y) => y - x)
    if (values.length > 1 && (values[0] ?? 0) - (values[1] ?? 0) < 0.05) close += 1
  }
  ms.sort((x, y) => x - y)
  return {
    meanChoice: chosen.length ? chosen.reduce((t, v) => t + v, 0) / chosen.length : null,
    closeShare: asked ? close / asked : null,
    median: quantile(ms, 0.5),
    p95: quantile(ms, 0.95),
    requests: ms.length,
  }
}

// --- presentation -------------------------------------------------------------------------------------------

/** Pieces and macro decisions are counted from 1 ("piece 34" is being decided); game steps and frames are clock
 * readings from 0. An event at position p happened with the p-th piece. */
export function countsFromOne(unit: string): boolean {
  return unit === 'piece' || unit === 'decision'
}

export function currentLabel(unit: string, position: number): string {
  return `${unit} ${countsFromOne(unit) ? position + 1 : position}`
}

export function formatScore(game: string, value: number): string {
  if (game === 'pong') return value > 0 ? `+${value}` : value < 0 ? `${MINUS}${-value}` : '0'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

const ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']

export function ordinal(n: number): string {
  return ORDINALS[n - 1] ?? `${n}th`
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export interface Caption {
  side: Side | null
  /** Where and whose: "Piece 34 · Clef". */
  header: string
  headline: string
  scope: string
}

export interface CaptionContext {
  game: string
  unit: string
  names: Record<Side, string>
  /** How each run ended, from versus.json ("topped out", "hit the wall", ...). */
  ends: Record<Side, string>
}

function needed(game: string, gap: number): string {
  const n = gap + 1
  const what = game === 'tetris' ? (n === 1 ? 'line' : 'lines') : game === 'snake' ? 'food' : n === 1 ? 'point' : 'points'
  return `${n} more ${what}`
}

/** One caption at a time: the latest event within `window` positions; during a chase, the chase itself. */
export function captionAt(events: readonly MatchEvent[], position: number, window: number, context: CaptionContext): Caption | null {
  const { game, unit, names } = context
  const score = (value: number) => formatScore(game, value)
  let latest: MatchEvent | undefined
  for (const event of events) {
    if (event.position > position) break
    if (event.kind === 'end' && events.some((e) => e.kind === 'chase' && e.position === event.position)) continue
    latest = event
  }
  const chase = events.find((e) => e.kind === 'chase' && e.position <= position)
  const at = (event: MatchEvent) => `${capital(unit)} ${event.position}`
  if (latest && position - latest.position <= window) {
    const who = latest.side ? names[latest.side] : ''
    const lead = latest.side === 'a' ? `${score(latest.a)} to ${score(latest.b)}` : `${score(latest.b)} to ${score(latest.a)}`
    switch (latest.kind) {
      case 'first':
        return { side: latest.side, header: `${at(latest)} · ${who}`, headline: `${who} goes ahead first, ${lead}.`, scope: 'The first difference between the two runs.' }
      case 'lead':
        return {
          side: latest.side,
          header: `${at(latest)} · ${who}`,
          headline: `${who} takes the lead, ${lead}.`,
          scope: `${capital(ordinal(latest.nth ?? 1))} change of lead in this game.`,
        }
      case 'level':
        return { side: null, header: at(latest), headline: `Level at ${score(latest.a)}.`, scope: 'Neither run is ahead.' }
      case 'end': {
        const side = latest.side ?? 'a'
        const final = side === 'a' ? latest.a : latest.b
        return { side, header: `${at(latest)} · ${names[side]}`, headline: `${names[side]} ${context.ends[side] || 'stops'} with ${score(final)}.`, scope: 'Its board stays on the last position.' }
      }
      case 'chase':
        break
    }
  }
  if (chase?.side) {
    const survivor = chase.side
    const stopped: Side = survivor === 'a' ? 'b' : 'a'
    const current = survivor === 'a' ? chase.a : chase.b
    const target = chase.target ?? 0
    return {
      side: survivor,
      header: `${capital(currentLabel(unit, position))} · ${names[survivor]}`,
      headline: `${names[survivor]} needs ${needed(game, target - current)} to win.`,
      scope: `${names[stopped]} ${context.ends[stopped] || 'stopped'} at ${unit} ${chase.position} with ${score(target)}.`,
    }
  }
  return null
}

export interface DiffPaths {
  above: string
  below: string
  maximum: number
}

/** Filled step areas of a - b up to `upto`, above the middle line where a leads and below where b does. */
export function diffPaths(a: Series, b: Series, last: number, upto: number, width = 1000, middle = 60, room = 48): DiffPaths {
  const positions = positionsOf(a, b).filter((p) => p <= upto)
  let maximum = 1
  for (const p of positions) maximum = Math.max(maximum, Math.abs(scoreAt(a, p) - scoreAt(b, p)))
  const x = (p: number) => (last > 0 ? (Math.min(p, last) / last) * width : 0).toFixed(1)
  let above = `M0,${middle}`
  let below = `M0,${middle}`
  positions.forEach((p, i) => {
    const next = positions[i + 1] ?? upto
    const d = scoreAt(a, p) - scoreAt(b, p)
    const yUp = (middle - (Math.max(d, 0) / maximum) * room).toFixed(1)
    const yDown = (middle + (Math.max(-d, 0) / maximum) * room).toFixed(1)
    above += ` L${x(p)},${yUp} L${x(next)},${yUp}`
    below += ` L${x(p)},${yDown} L${x(next)},${yDown}`
  })
  above += ` L${x(upto)},${middle} Z`
  below += ` L${x(upto)},${middle} Z`
  return { above, below, maximum }
}

// --- versus.json helpers -------------------------------------------------------------------------------------

export function gameKey(board: string, game: string): string {
  return `${board}/${game}`
}

export interface SeedRow {
  seed: number
  a: VersusEpisode | null
  b: VersusEpisode | null
  leadChanges: number | null
  chase: boolean
  /** a - b, in the orientation asked for. */
  margin: number | null
  /** Both runs ended on the game's floor (every point lost, no line): nothing to compare. */
  floored: boolean
}

/** Every seed both models played, with the pair's comparison oriented as (a, b). */
export function seedRows(data: VersusData, board: string, game: string, a: string, b: string): SeedRow[] {
  const key = gameKey(board, game)
  const episodes = data.episodes[key] ?? {}
  const flip = pairId(a, b) !== `${a}~${b}`
  const rows = data.matches[key]?.[pairId(a, b)] ?? {}
  const seeds = data.games.find((g) => g.board === board && g.game === game)?.seeds ?? []
  const floor = data.floors[key]
  return seeds.map((seed) => {
    const row = rows[String(seed)]
    const ea = episodes[a]?.[String(seed)] ?? null
    const eb = episodes[b]?.[String(seed)] ?? null
    return {
      seed,
      a: ea,
      b: eb,
      leadChanges: row ? row[0] : null,
      chase: row ? row[1] === 1 : false,
      margin: row ? (flip ? 0 - row[2] : row[2]) : null,
      floored: floor !== undefined && ea?.[0] === floor && eb?.[0] === floor,
    }
  })
}

export interface Record3 {
  wins: number
  draws: number
  losses: number
}

export function seriesRecord(rows: readonly SeedRow[]): Record3 {
  const record = { wins: 0, draws: 0, losses: 0 }
  for (const row of rows) {
    if (!row.a || !row.b) continue
    if (row.a[0] > row.b[0]) record.wins += 1
    else if (row.a[0] < row.b[0]) record.losses += 1
    else record.draws += 1
  }
  return record
}

/** Why a seed is worth watching, from its comparison alone (no replay needed). */
export function whyWatch(row: SeedRow, names: Record<Side, string>): string {
  if (!row.a || !row.b) return ''
  if (row.floored) return 'both end on the floor'
  const parts: string[] = []
  if (row.leadChanges) parts.push(`${row.leadChanges} lead change${row.leadChanges === 1 ? '' : 's'}`)
  if (row.chase) parts.push('a chase after one run stops')
  if (row.margin === 0 && row.a[0] !== 0) parts.push('level at the end')
  else if (row.margin !== null && Math.abs(row.margin) === 1) parts.push(`won by one`)
  const longer = (row.a[1] ?? 0) - (row.b[1] ?? 0)
  if (!parts.length && Math.abs(longer) >= 20) parts.push(`${longer > 0 ? names.a : names.b} plays on alone for ${Math.abs(longer)}`)
  return parts.join(' · ')
}
