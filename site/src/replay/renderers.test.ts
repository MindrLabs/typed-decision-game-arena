import { describe, expect, it } from 'vitest'

import { LANDINGS } from '../test/fixtures'
import { FALLBACK_PALETTE } from './palette'
import { bandOf, canDraw, describeSnapshot, drawSnapshot, landingOf } from './renderers'

const tetris = {
  board: Array.from({ length: 20 }, () => '..........'),
  piece: { kind: 'T', cells: [[0, 4]] },
  next: 'S',
  lines: 3,
  pieces: 9,
  over: false,
}
const snake = { size: 10, snake: [[4, 4], [5, 4], [6, 4]], food: [1, 1], heading: 'up', eaten: 2, alive: true }
const connect4 = { grid: ['.......', '.......', '.......', '.......', '.......', '..XO...'], you: 'O', opponent: 'win-block', last: 4, result: null }
const pong = { field: [160, 160], ball: null, player: [60, 75], opponent: [10, 25], score: [3, 5] }
const breakout = { field: [144, 161], ball: [10, 100], paddle: [40, 55], lives: 4, score: 12, bricks: ['#'.repeat(18), '#.'.repeat(9), '', '', '', ''] }

describe('canDraw', () => {
  it('accepts each game’s snapshot and rejects mismatches', () => {
    expect(canDraw('tetris', tetris)).toBe(true)
    expect(canDraw('snake', snake)).toBe(true)
    expect(canDraw('connect4', connect4)).toBe(true)
    expect(canDraw('pong', pong)).toBe(true)
    expect(canDraw('breakout', breakout)).toBe(true)
    expect(canDraw('tetris', snake)).toBe(false)
    expect(canDraw('chess', tetris)).toBe(false)
    expect(canDraw('pong', null)).toBe(false)
  })
})

describe('describeSnapshot', () => {
  it('summarises each game in one line', () => {
    expect(describeSnapshot('tetris', tetris)).toBe('3 lines, 9 pieces placed, current T, next S')
    expect(describeSnapshot('snake', snake)).toBe('2 food eaten, length 3, heading up')
    expect(describeSnapshot('connect4', connect4)).toBe('playing O against win-block, last move in column 4')
    expect(describeSnapshot('pong', pong)).toBe('you 3, opponent 5, no ball in play')
    expect(describeSnapshot('breakout', breakout)).toBe('score 12, 4 lives, 27 bricks standing')
    expect(describeSnapshot('tetris', {})).toBe('unrecognised snapshot')
  })
})

describe('bandOf', () => {
  it('maps macro band keys to field ranges', () => {
    expect(bandOf('pong', 'zone1')).toEqual([0, 19])
    expect(bandOf('pong', 'zone5')).toEqual([80, 99])
    expect(bandOf('breakout', 'zone8')).toEqual([126, 143])
  })

  it('ignores other keys and games', () => {
    expect(bandOf('pong', 'up')).toBeUndefined()
    expect(bandOf('pong', 'zone9')).toBeUndefined()
    expect(bandOf('tetris', 'zone1')).toBeUndefined()
  })
})

describe('landingOf', () => {
  const macro = { ...tetris, landings: LANDINGS }

  it('reads an option’s landing from a macro Tetris snapshot', () => {
    expect(landingOf(macro, 'cw-c2')).toEqual(LANDINGS['cw-c2'])
  })

  it('has nothing for frame snapshots, unknown keys or other games', () => {
    expect(landingOf(tetris, 'cw-c2')).toBeUndefined()
    expect(landingOf(macro, 'nope')).toBeUndefined()
    expect(landingOf(macro, null)).toBeUndefined()
    expect(landingOf(snake, 'cw-c2')).toBeUndefined()
  })
})

/** A 2D context that records the calls made on it. */
function recordingContext() {
  const calls: string[] = []
  const target: Record<string, unknown> = {}
  const context = new Proxy(target, {
    get(store, name: string) {
      if (name in store) return store[name]
      return (...args: unknown[]) => {
        calls.push(`${name}(${args.length})`)
      }
    },
    set(store, name: string, value: unknown) {
      store[name] = value
      return true
    },
  })
  return { context: context as unknown as CanvasRenderingContext2D, calls }
}

describe('drawSnapshot', () => {
  const size = { width: 200, height: 400 }
  const macro = { ...tetris, landings: LANDINGS }
  const strokes = (calls: string[]) => calls.filter((call) => call.startsWith('strokeRect')).length

  it('outlines the chosen landing and a different previewed one, cell by cell', () => {
    const plain = recordingContext()
    drawSnapshot(plain.context, 'tetris', macro, FALLBACK_PALETTE, size)
    const ghost = recordingContext()
    drawSnapshot(ghost.context, 'tetris', macro, FALLBACK_PALETTE, size, { ghost: LANDINGS['spawn-c8'] })
    const both = recordingContext()
    drawSnapshot(both.context, 'tetris', macro, FALLBACK_PALETTE, size, {
      ghost: LANDINGS['spawn-c8'],
      preview: LANDINGS['cw-c2'],
    })
    expect(strokes(plain.calls)).toBe(0)
    expect(strokes(ghost.calls)).toBe(4)
    expect(strokes(both.calls)).toBe(8)
  })

  it('draws nothing on a canvas too small to hold the board', () => {
    const tiny = recordingContext()
    drawSnapshot(tiny.context, 'tetris', macro, FALLBACK_PALETTE, { width: 10, height: 20 }, { ghost: LANDINGS['cw-c2'] })
    expect(tiny.calls).toEqual(['clearRect(4)'])
  })
})
