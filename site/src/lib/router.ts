import { useSyncExternalStore } from 'react'

/** Hash routes: the site is served by plain static file servers, which cannot rewrite paths. */
export type Route =
  | { name: 'board'; board: string | null }
  | { name: 'model'; player: string }
  | { name: 'replay'; board: string; game: string; player: string; seed: number }
  | { name: 'method' }
  | { name: 'versus'; board: string | null; game: string | null; a: string | null; b: string | null }
  | { name: 'match'; board: string; game: string; a: string; b: string; seed: number }
  | { name: 'duel'; a: string; b: string; seed: number; gameNo: number }
  | { name: 'notfound'; path: string }

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '').replace(/^\/+/, '').replace(/\/+$/, '')
  const parts = path === '' ? [] : path.split('/').map((part) => decodeURIComponent(part))
  const [head, ...rest] = parts
  if (head === undefined) return { name: 'board', board: null }
  if (head === 'board' && rest.length === 1 && rest[0]) return { name: 'board', board: rest[0] }
  if (head === 'model' && rest.length === 1 && rest[0]) return { name: 'model', player: rest[0] }
  if (head === 'method' && rest.length === 0) return { name: 'method' }
  if (head === 'versus') {
    if (rest.length === 0) return { name: 'versus', board: null, game: null, a: null, b: null }
    const [board, game, a, b, seedText] = rest
    if (rest.length === 4 && board && game && a && b) return { name: 'versus', board, game, a, b }
    const seed = Number(seedText)
    if (rest.length === 5 && board && game && a && b && Number.isInteger(seed)) return { name: 'match', board, game, a, b, seed }
  }
  if (head === 'duel' && rest.length === 4) {
    const [a, b, seedText, gameText] = rest
    const seed = Number(seedText)
    const gameNo = Number(gameText)
    if (a && b && Number.isInteger(seed) && (gameNo === 1 || gameNo === 2)) return { name: 'duel', a, b, seed, gameNo }
  }
  if (head === 'replay' && rest.length === 4) {
    const [board, game, player, seedText] = rest
    const seed = Number(seedText)
    if (board && game && player && Number.isInteger(seed)) return { name: 'replay', board, game, player, seed }
  }
  return { name: 'notfound', path }
}

const encode = encodeURIComponent

export const href = {
  home: '#/',
  board: (board: string) => `#/board/${encode(board)}`,
  model: (player: string) => `#/model/${encode(player)}`,
  replay: (board: string, game: string, player: string, seed: number) =>
    `#/replay/${encode(board)}/${encode(game)}/${encode(player)}/${seed}`,
  method: '#/method',
  versus: '#/versus',
  versusPick: (board: string, game: string, a: string, b: string) =>
    `#/versus/${encode(board)}/${encode(game)}/${encode(a)}/${encode(b)}`,
  match: (board: string, game: string, a: string, b: string, seed: number) =>
    `#/versus/${encode(board)}/${encode(game)}/${encode(a)}/${encode(b)}/${seed}`,
  /** A direct game; `a` is shown on the left whichever colour it plays. */
  duel: (a: string, b: string, seed: number, gameNo: number) => `#/duel/${encode(a)}/${encode(b)}/${seed}/${gameNo}`,
}

function subscribe(callback: () => void): () => void {
  window.addEventListener('hashchange', callback)
  return () => {
    window.removeEventListener('hashchange', callback)
  }
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => '',
  )
  return parseHash(hash)
}
