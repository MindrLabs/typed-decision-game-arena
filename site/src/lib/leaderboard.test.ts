import { describe, expect, it } from 'vitest'

import { makeIndex } from '../test/fixtures'
import {
  boardLatency,
  boardTable,
  delaySteps,
  findBoard,
  findReplay,
  heatBackground,
  isDevelopmentData,
  latencyFor,
  replaysOf,
} from './leaderboard'

const index = makeIndex()
const macro = findBoard(index, 'macro')
const realtime = findBoard(index, 'realtime')
if (!macro || !realtime) throw new Error('fixture boards missing')

describe('boardTable', () => {
  const table = boardTable(index, macro)

  it('keeps the index order and ranks models among themselves', () => {
    expect(table.ranked.map((row) => row.id)).toEqual(['reference', 'model-a', 'random'])
    expect(table.ranked.map((row) => row.modelRank)).toEqual([null, 1, null])
    expect(table.ranked.filter((row) => row.isAnchor).map((row) => row.id)).toEqual(['reference', 'random'])
    expect(table.hasModels).toBe(true)
  })

  it('lists players without an index separately', () => {
    expect(table.incomplete.map((row) => row.id)).toEqual(['model-b'])
  })

  it('handles boards without results', () => {
    const empty = boardTable(index, realtime)
    expect(empty.ranked).toEqual([])
    expect(empty.hasModels).toBe(false)
  })
})

describe('latency', () => {
  it('reads the board/game key of the latency file', () => {
    expect(latencyFor(index, 'model-a', macro, 'tetris')).toBe(40)
    expect(latencyFor(index, 'random', macro, 'tetris')).toBeUndefined()
  })

  it('uses the frame measurements on the real-time board', () => {
    expect(latencyFor(index, 'model-a', realtime, 'tetris')).toBe(150)
  })

  it('summarises a board by the median of its games', () => {
    expect(boardLatency(index, 'model-a', macro)).toBe(35)
    expect(boardLatency(index, 'model-a', realtime)).toBe(150)
    expect(boardLatency(index, 'model-b', macro)).toBeUndefined()
  })

  it('converts latency into real-time reaction steps', () => {
    expect(delaySteps(10)).toBe(1)
    expect(delaySteps(66.6)).toBe(1)
    expect(delaySteps(150)).toBe(3)
  })
})

describe('helpers', () => {
  it('shades heat cells in proportion to k and leaves missing ones plain', () => {
    expect(heatBackground(undefined)).toBeUndefined()
    expect(heatBackground(0)).toContain('6%')
    expect(heatBackground(1)).toContain('68%')
    expect(heatBackground(3)).toContain('68%')
  })

  it('finds replays', () => {
    expect(replaysOf(index, { player: 'model-a' })).toHaveLength(2)
    expect(replaysOf(index, { board: 'macro', game: 'pong' })).toHaveLength(1)
    expect(findReplay(index, 'macro', 'tetris', 'model-a', 1001)?.path).toBe('replays/macro/tetris/model-a/1001.json.gz')
    expect(findReplay(index, 'macro', 'tetris', 'model-a', 7)).toBeUndefined()
  })

  it('flags development data', () => {
    expect(isDevelopmentData(index)).toBe(true)
    expect(isDevelopmentData(makeIndex({ seed_set: 'test', suite: { ...index.suite, frozen: true, lock: 'abc' } }))).toBe(false)
    expect(isDevelopmentData(makeIndex({ seed_set: 'test' }))).toBe(true)
  })
})
