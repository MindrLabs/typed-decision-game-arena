// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { makeIndex, makeReplay } from '../test/fixtures'
import { defaultSpeed, ReplayView } from './ReplayView'

beforeAll(() => {
  // jsdom has neither layout observers nor a 2D canvas; the view must cope without drawing.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {
        return undefined
      }
      disconnect() {
        return undefined
      }
    },
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function counter() {
  return screen.getByText(/^decision \d+ \/ \d+$/).textContent
}

describe('ReplayView', () => {
  it('shows the decision, the requests and their probabilities', () => {
    render(<ReplayView index={makeIndex()} replay={makeReplay()} />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Tetris')
    expect(counter()).toBe('decision 1 / 3')
    expect(screen.getByText('single')).toBeTruthy()
    expect(screen.getByLabelText('probability 0.700')).toBeTruthy()
    expect(screen.getByRole('slider', { name: 'Decision' })).toBeTruthy()
  })

  it('steps with the keyboard and the slider', () => {
    render(<ReplayView index={makeIndex()} replay={makeReplay({ final: null })} />)
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(counter()).toBe('decision 2 / 3')
    fireEvent.keyDown(window, { key: 'End' })
    expect(counter()).toBe('decision 3 / 3')
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(counter()).toBe('decision 3 / 3')
    fireEvent.change(screen.getByRole('slider', { name: 'Decision' }), { target: { value: '0' } })
    expect(counter()).toBe('decision 1 / 3')
  })

  it('plays to the end and offers to replay', () => {
    vi.useFakeTimers()
    render(<ReplayView index={makeIndex()} replay={makeReplay()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    expect(screen.getByRole('button', { name: 'Pause' })).toBeTruthy()
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByText('end of game')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Play' }).textContent).toBe('Replay')
  })

  it('ends with the position after the last move', () => {
    render(<ReplayView index={makeIndex()} replay={makeReplay()} />)
    fireEvent.keyDown(window, { key: 'End' })
    expect(screen.getByText('end of game')).toBeTruthy()
    const aside = screen.getByRole('complementary', { name: 'End of game' })
    expect(aside.textContent).toContain('Final score 41(lines cleared)')
    expect(aside.textContent).toContain('topped outno')
    expect(screen.queryByText('Requests')).toBeNull()
    expect(screen.getByRole('slider', { name: 'Decision' }).getAttribute('aria-valuetext')).toBe('end of game, step 3')
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(counter()).toBe('decision 3 / 3')
  })

  it('plays older exports without a final position', () => {
    render(<ReplayView index={makeIndex()} replay={makeReplay({ final: null })} />)
    fireEvent.keyDown(window, { key: 'End' })
    expect(counter()).toBe('decision 3 / 3')
    expect(screen.queryByText('end of game')).toBeNull()
  })

  it('previews an option’s landing while it is pointed at', () => {
    render(<ReplayView index={makeIndex()} replay={makeReplay()} />)
    expect(screen.getByText(/outlined cells are where the chosen placement lands/)).toBeTruthy()
    const option = screen.getByText('cw-c2', { selector: 'li > span' }).closest('li')
    if (!option) throw new Error('option not rendered')
    expect(option.getAttribute('tabindex')).toBe('0')
    fireEvent.mouseEnter(option)
    fireEvent.mouseLeave(option)
  })

  it('picks a playback speed per board and game', () => {
    expect(defaultSpeed({ board: 'frame', game: 'pong' })).toBe(20)
    expect(defaultSpeed({ board: 'macro', game: 'connect4' })).toBe(1)
    expect(defaultSpeed({ board: 'macro', game: 'tetris' })).toBe(5)
  })
})
