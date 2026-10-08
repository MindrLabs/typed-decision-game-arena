// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { makeIndex } from '../test/fixtures'
import { LeaderboardView } from './LeaderboardPage'

afterEach(() => {
  cleanup()
})

describe('LeaderboardView', () => {
  it('ranks models, marks anchors and shows per-game scores', () => {
    render(<LeaderboardView index={makeIndex()} boardId="macro" />)

    expect(screen.getByRole('heading', { name: 'Leaderboard' })).toBeTruthy()
    expect(screen.getByRole('note').textContent).toContain('Development data')

    const table = screen.getAllByRole('table')[0]
    if (!table) throw new Error('no leaderboard table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => within(row).getAllByRole('link')[0]?.textContent)).toEqual(['Reference', 'Model A', 'Random'])

    const [anchorRow, modelRow] = rows
    if (!anchorRow || !modelRow) throw new Error('missing rows')
    const cells = within(modelRow).getAllByRole('cell')
    expect(cells[0]?.textContent).toBe('1')
    expect(cells[2]?.textContent).toContain('45.0')
    expect(cells[3]?.textContent).toBe('40.0')
    expect(cells[4]?.textContent).toBe('50.0')
    expect(cells[5]?.textContent).toBe('35 ms')
    expect(within(anchorRow).getByText('anchor')).toBeTruthy()

    expect(screen.getByRole('heading', { name: 'Incomplete runs' })).toBeTruthy()
    expect(screen.getByText('1/2 seeds')).toBeTruthy()
    expect(screen.getByText(/Pairwise differences/)).toBeTruthy()
  })

  it('links each model row to its replays', () => {
    render(<LeaderboardView index={makeIndex()} boardId="macro" />)
    const link = screen.getByRole('link', { name: 'Model A: Tetris replay, seed 1001' })
    expect(link.getAttribute('href')).toBe('#/replay/macro/tetris/model-a/1001')
  })

  it('explains an empty board', () => {
    render(<LeaderboardView index={makeIndex()} boardId="realtime" />)
    expect(screen.getByRole('heading', { name: 'No model has finished this board yet' })).toBeTruthy()
    expect(screen.getByText(/arena latency --player/)).toBeTruthy()
  })

  it('falls back to the first board for an unknown id and hides the banner for published data', () => {
    const index = makeIndex({ seed_set: 'test', suite: { ...makeIndex().suite, frozen: true, lock: 'abc' } })
    render(<LeaderboardView index={index} boardId="nope" />)
    expect(screen.getByRole('heading', { name: 'Macro board' })).toBeTruthy()
    expect(screen.queryByText('Development data')).toBeNull()
  })
})
