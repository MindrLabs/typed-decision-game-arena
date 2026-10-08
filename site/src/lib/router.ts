import { useSyncExternalStore } from 'react'

/** Hash routes: the site is served by plain static file servers, which cannot rewrite paths. */
export type Route =
  | { name: 'board'; board: string | null }
  | { name: 'model'; player: string }
  | { name: 'replay'; board: string; game: string; player: string; seed: number }
  | { name: 'method' }
  | { name: 'notfound'; path: string }

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '').replace(/^\/+/, '').replace(/\/+$/, '')
  const parts = path === '' ? [] : path.split('/').map((part) => decodeURIComponent(part))
  const [head, ...rest] = parts
  if (head === undefined) return { name: 'board', board: null }
  if (head === 'board' && rest.length === 1 && rest[0]) return { name: 'board', board: rest[0] }
  if (head === 'model' && rest.length === 1 && rest[0]) return { name: 'model', player: rest[0] }
  if (head === 'method' && rest.length === 0) return { name: 'method' }
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
