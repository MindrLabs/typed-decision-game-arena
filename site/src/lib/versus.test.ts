import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import type { ReplayDecision, VersusData } from './types'
import {
  captionAt,
  compare,
  diffPaths,
  endsTheGame,
  framesOf,
  lastAtOrBefore,
  matchEvents,
  pairId,
  scoreAt,
  scoreOf,
  seedRows,
  seriesRecord,
  shownEvents,
  snakeTarget,
  styleOf,
  tetrisStack,
  topOptions,
  type Series,
} from './versus'

interface GoldenCase {
  name: string
  a: Series
  b: Series
  lead_changes: number
  chase: boolean
  margin: number
}

const golden = JSON.parse(readFileSync(new URL('../../../tests/golden/versus-series.json', import.meta.url), 'utf8')) as {
  cases: GoldenCase[]
}

describe('compare (shared with arena/versus.py)', () => {
  it.each(golden.cases)('$name', (c) => {
    const result = compare(c.a, c.b)
    expect(result.leadChanges).toBe(c.lead_changes)
    expect(result.chase).toBe(c.chase)
    expect(result.margin).toBe(c.margin)
  })
})

const [chaseCase] = golden.cases
if (!chaseCase) throw new Error('tests/golden/versus-series.json has no cases')

describe('match events', () => {
  it('marks the first score, each change of lead, a level score, the ends and the chase', () => {
    const events = matchEvents(chaseCase.a, chaseCase.b)
    expect(events.map((e) => `${e.position}:${e.kind}:${e.side ?? '-'}`)).toEqual([
      '4:first:a',
      '9:level:-',
      '11:lead:b',
      '12:level:-',
      '21:end:b',
      '21:chase:a',
      '34:lead:a',
      '35:end:a',
    ])
    expect(events.find((e) => e.kind === 'chase')?.target).toBe(2)
  })

  it('hides level scores in a busy match', () => {
    const busy = matchEvents(
      { points: Array.from({ length: 16 }, (_, i): [number, number] => [i * 2, i % 2 === 0 ? 0 : 1]), end: 40, final: 0 },
      { points: Array.from({ length: 16 }, (_, i): [number, number] => [i * 2 + 1, i % 2 === 0 ? 1 : 0]), end: 40, final: 0 },
    )
    expect(busy.some((e) => e.kind === 'level')).toBe(true)
    expect(shownEvents(busy).some((e) => e.kind === 'level')).toBe(false)
    expect(shownEvents(matchEvents(chaseCase.a, chaseCase.b)).filter((e) => e.kind === 'level')).toHaveLength(2)
  })

  it('writes one caption at a time, then the chase', () => {
    const events = matchEvents(chaseCase.a, chaseCase.b)
    const context = { game: 'tetris', unit: 'piece', names: { a: 'Clef', b: 'Nimble' }, ends: { a: 'tops out', b: 'tops out' } }
    expect(captionAt(events, 11, 3, context)?.headline).toBe('Nimble takes the lead, 2 to 1.')
    expect(captionAt(events, 30, 3, context)?.headline).toBe('Clef needs 1 more line to win.')
    expect(captionAt(events, 34, 3, context)?.scope).toBe('Second change of lead in this game.')
    expect(captionAt(events, 2, 3, context)).toBeNull()
  })
})

describe('series helpers', () => {
  const series: Series = { points: [[0, 0], [3, 1]], end: 5, final: 2 }

  it('holds the latest score and the final one after the end', () => {
    expect([0, 2, 3, 4, 5, 9].map((p) => scoreAt(series, p))).toEqual([0, 0, 1, 1, 2, 2])
  })

  it('steps through every decision, or the union of steps on the real-time board', () => {
    expect(framesOf(series, { points: [[0, 0]], end: 3, final: 0 }, 'decision')).toEqual([0, 1, 2, 3, 4, 5])
    expect(framesOf(series, { points: [[0, 0], [4, 1]], end: 7, final: 1 }, 'step')).toEqual([0, 3, 4, 5, 7])
  })

  it('finds the last decision at or before a position', () => {
    expect(lastAtOrBefore([0, 4, 8], 0)).toBe(0)
    expect(lastAtOrBefore([0, 4, 8], 7)).toBe(1)
    expect(lastAtOrBefore([0, 4, 8], 99)).toBe(2)
    expect(lastAtOrBefore([2], 1)).toBe(-1)
  })

  it('draws the difference above and below the middle line', () => {
    const paths = diffPaths(chaseCase.a, chaseCase.b, 35, 12)
    expect(paths.maximum).toBe(1)
    expect(paths.above).toContain('L114.3,12.0')
    expect(paths.below).toContain('L314.3,108.0')
  })
})

describe('game readings', () => {
  it('reads running scores', () => {
    expect(scoreOf('tetris', { lines: 3 })).toBe(3)
    expect(scoreOf('pong', { score: [2, 16] })).toBe(-14)
    expect(scoreOf('breakout', { score: 29 })).toBe(29)
  })

  it('measures a Tetris stack', () => {
    expect(tetrisStack(['....', '.#..', '....', '##.#'])).toEqual({ height: 3, holes: 1 })
  })

  it('reads Snake option targets and fatal moves', () => {
    expect(snakeTarget('go straight: the head moves north to row 4, column 8; the cell is empty')).toEqual([3, 7])
    expect(endsTheGame("the snake's body is there, so the game ends")).toBe(true)
    expect(endsTheGame('turn right: the head would leave the grid to the east, so the game ends')).toBe(true)
  })

  const decision = (p: Record<string, number> | null, choice: string, ms = [100]): ReplayDecision => ({
    i: 0,
    step: 0,
    snapshot: {},
    state: '',
    instructions: '',
    options: [
      { key: 'a', text: 'option a' },
      { key: 'b', text: 'option b' },
    ],
    calls: ms.map((m, i) => ({ stage: i === ms.length - 1 ? 'final' : 'group', keys: ['a', 'b'], choice, p, ms: m })),
    choice,
    forced: false,
  })

  it('ranks options and summarises a decision style', () => {
    expect(topOptions(decision({ a: 0.3, b: 0.7 }, 'b')).map((o) => o.key)).toEqual(['b', 'a'])
    expect(topOptions(decision(null, 'a'))).toEqual([{ key: 'a', p: null, text: 'option a' }])
    const style = styleOf([decision({ a: 0.52, b: 0.48 }, 'a', [100, 300]), decision({ a: 0.9, b: 0.1 }, 'a', [200])], 2)
    expect(style.meanChoice).toBeCloseTo(0.71)
    expect(style.closeShare).toBe(0.5)
    expect(style.requests).toBe(3)
    expect(style.median).toBe(200)
  })
})

describe('versus.json rows', () => {
  const data = {
    games: [{ board: 'macro', game: 'tetris', sync: 'decision', unit: 'piece', seeds: [1, 2, 3] }],
    episodes: {
      'macro/tetris': {
        clef: { '1': [3, 35, 'topped out'], '2': [0, 20, 'topped out'], '3': [0, 12, 'topped out'] },
        nimble: { '1': [2, 21, 'topped out'], '2': [1, 30, 'topped out'], '3': [0, 14, 'topped out'] },
      },
    },
    matches: { 'macro/tetris': { 'clef~nimble': { '1': [2, 1, 1], '2': [0, 0, -1], '3': [0, 0, 0] } } },
    floors: { 'macro/tetris': 0 },
  } as unknown as VersusData

  it('orients a pair as asked and counts the series', () => {
    expect(pairId('nimble', 'clef')).toBe('clef~nimble')
    const rows = seedRows(data, 'macro', 'tetris', 'nimble', 'clef')
    expect(rows.map((r) => r.margin)).toEqual([-1, 1, 0])
    expect(rows[0]?.chase).toBe(true)
    expect(rows.map((r) => r.floored)).toEqual([false, false, true])
    expect(seriesRecord(rows)).toEqual({ wins: 1, draws: 1, losses: 1 })
  })
})
