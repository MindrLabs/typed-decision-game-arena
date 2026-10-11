import { describe, expect, it } from 'vitest'

import { href, parseHash } from './router'

describe('parseHash', () => {
  it('maps the empty hash to the default board', () => {
    expect(parseHash('')).toEqual({ name: 'board', board: null })
    expect(parseHash('#/')).toEqual({ name: 'board', board: null })
  })

  it('parses every route', () => {
    expect(parseHash('#/board/frame')).toEqual({ name: 'board', board: 'frame' })
    expect(parseHash('#/model/kev-0.8b')).toEqual({ name: 'model', player: 'kev-0.8b' })
    expect(parseHash('#/method')).toEqual({ name: 'method' })
    expect(parseHash('#/replay/macro/tetris/kev-0.8b/1001')).toEqual({
      name: 'replay',
      board: 'macro',
      game: 'tetris',
      player: 'kev-0.8b',
      seed: 1001,
    })
  })

  it('round-trips the links it builds', () => {
    expect(parseHash(href.model('a b/c'))).toEqual({ name: 'model', player: 'a b/c' })
    expect(parseHash(href.replay('frame', 'pong', 'clef', 3))).toMatchObject({ name: 'replay', seed: 3 })
  })

  it('parses the Versus routes', () => {
    expect(parseHash('#/versus')).toEqual({ name: 'versus', board: null, game: null, a: null, b: null })
    expect(parseHash(href.versusPick('macro', 'snake', 'nimble', 'clef'))).toEqual({ name: 'versus', board: 'macro', game: 'snake', a: 'nimble', b: 'clef' })
    expect(parseHash(href.match('frame', 'pong', 'clef', 'nimble-v2', 3))).toEqual({
      name: 'match',
      board: 'frame',
      game: 'pong',
      a: 'clef',
      b: 'nimble-v2',
      seed: 3,
    })
    expect(parseHash(href.duel('nimble', 'clef', 7, 2))).toEqual({ name: 'duel', a: 'nimble', b: 'clef', seed: 7, gameNo: 2 })
    expect(parseHash('#/duel/nimble/clef/7/3')).toMatchObject({ name: 'notfound' })
  })

  it('rejects malformed paths', () => {
    expect(parseHash('#/replay/macro/tetris/x/abc')).toEqual({ name: 'notfound', path: 'replay/macro/tetris/x/abc' })
    expect(parseHash('#/nowhere')).toMatchObject({ name: 'notfound' })
  })
})
