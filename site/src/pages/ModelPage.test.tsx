// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { makeIndex } from '../test/fixtures'
import { ModelView } from './ModelPage'

afterEach(() => {
  cleanup()
})

describe('ModelView', () => {
  it('shows the checkpoint, the results per board, latency and replays', () => {
    render(<ModelView index={makeIndex()} playerId="model-a" />)
    expect(screen.getByRole('heading', { level: 1, name: 'Model A' })).toBeTruthy()

    const checkpoint = screen.getByRole('link', { name: /org\/model-a/ })
    expect(checkpoint.getAttribute('href')).toBe('https://huggingface.co/org/model-a/tree/0123456789abcdef0123')

    expect(screen.getByText(/rank 1 of 1 model$/)).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Latency' })).toBeTruthy()
    expect(screen.getByText('macro/tetris')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /seed 1001/ })).toHaveLength(2)
  })

  it('labels anchors and handles unknown players', () => {
    const { unmount } = render(<ModelView index={makeIndex()} playerId="reference" />)
    expect(screen.getByText(/· anchor$/)).toBeTruthy()
    unmount()
    render(<ModelView index={makeIndex()} playerId="nobody" />)
    expect(screen.getByRole('heading', { name: 'Unknown player' })).toBeTruthy()
  })
})
