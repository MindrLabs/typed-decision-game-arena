import { useSyncExternalStore } from 'react'

/** Canvas colours, read from the CSS variables in index.css so the games follow light and dark mode. */
export interface Palette {
  bg: string
  grid: string
  stack: string
  text: string
  dim: string
  snake: string
  snakeHead: string
  food: string
  board: string
  hole: string
  x: string
  o: string
  player: string
  opponent: string
  ball: string
  paddle: string
  band: string
  accent: string
}

const VARIABLES: Record<keyof Palette, string> = {
  bg: '--game-bg',
  grid: '--game-grid',
  stack: '--game-stack',
  text: '--game-text',
  dim: '--game-dim',
  snake: '--game-snake',
  snakeHead: '--game-snake-head',
  food: '--game-food',
  board: '--game-board',
  hole: '--game-hole',
  x: '--game-x',
  o: '--game-o',
  player: '--game-player',
  opponent: '--game-opponent',
  ball: '--game-ball',
  paddle: '--game-paddle',
  band: '--game-band',
  accent: '--accent',
}

export const FALLBACK_PALETTE: Palette = {
  bg: '#10181b',
  grid: '#1f2b30',
  stack: '#8aa0a8',
  text: '#e9f1f2',
  dim: '#6e8187',
  snake: '#2dd4bf',
  snakeHead: '#99f6e4',
  food: '#f87171',
  board: '#1d4ed8',
  hole: '#0b1220',
  x: '#ef4444',
  o: '#facc15',
  player: '#4ade80',
  opponent: '#fb923c',
  ball: '#f8fafc',
  paddle: '#ef6262',
  band: '#5eead4',
  accent: '#0f766e',
}

const DARK_QUERY = '(prefers-color-scheme: dark)'
const cache = new Map<boolean, Palette>()

function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement)
  const palette = { ...FALLBACK_PALETTE }
  for (const [key, variable] of Object.entries(VARIABLES) as [keyof Palette, string][]) {
    const value = style.getPropertyValue(variable).trim()
    if (value) palette[key] = value
  }
  return palette
}

function snapshot(): Palette {
  const dark = typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches
  let palette = cache.get(dark)
  if (!palette) {
    palette = readPalette()
    cache.set(dark, palette)
  }
  return palette
}

function subscribe(callback: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => undefined
  const query = window.matchMedia(DARK_QUERY)
  query.addEventListener('change', callback)
  return () => {
    query.removeEventListener('change', callback)
  }
}

export function usePalette(): Palette {
  return useSyncExternalStore(subscribe, snapshot, () => FALLBACK_PALETTE)
}
