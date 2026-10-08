import type { ArenaIndex, BoardInfo, BoardScores, PlayerInfo, PlayerScore, ReplayRef } from './types'

export interface Row {
  id: string
  player: PlayerInfo
  score: PlayerScore
  /** Baselines anchor every normalised score (random = 0, reference = 100). */
  isAnchor: boolean
  /** Rank among models only; anchors have none. */
  modelRank: number | null
}

export interface BoardTable {
  board: BoardInfo
  scores: BoardScores | undefined
  /** Ranked by index: models and the two anchors, in index order. */
  ranked: Row[]
  /** Players with results that do not cover every game and seed of the board yet. */
  incomplete: Row[]
  hasModels: boolean
}

const UNKNOWN_PLAYER: PlayerInfo = { title: '', kind: 'model', description: '' }

export function playerInfo(index: ArenaIndex, id: string): PlayerInfo {
  return index.players[id] ?? { ...UNKNOWN_PLAYER, title: id }
}

export function isBaseline(index: ArenaIndex, id: string): boolean {
  return playerInfo(index, id).kind === 'baseline'
}

export function findBoard(index: ArenaIndex, id: string | null | undefined): BoardInfo | undefined {
  return index.boards.find((board) => board.id === id)
}

export function boardTable(index: ArenaIndex, board: BoardInfo): BoardTable {
  const scores = index.scores[board.id]
  const players = scores?.players ?? {}
  const rankedIds = scores?.ranking ?? []
  let modelRank = 0
  const ranked = rankedIds.flatMap((id): Row[] => {
    const score = players[id]
    if (!score) return []
    const isAnchor = isBaseline(index, id)
    if (!isAnchor) modelRank += 1
    return [{ id, player: playerInfo(index, id), score, isAnchor, modelRank: isAnchor ? null : modelRank }]
  })
  const rankedSet = new Set(rankedIds)
  const incomplete = Object.entries(players)
    .filter(([id]) => !rankedSet.has(id))
    .map(([id, score]) => ({ id, player: playerInfo(index, id), score, isAnchor: isBaseline(index, id), modelRank: null }))
    .sort((a, b) => a.player.title.localeCompare(b.player.title))
  return { board, scores, ranked, incomplete, hasModels: ranked.some((row) => !row.isAnchor) }
}

/** Median latency (ms) of a player on one game of a board. The real-time board has no latency of its own: its
 * delays come from the frame board's measurements, which `anchor_board` names. */
export function latencyFor(index: ArenaIndex, player: string, board: BoardInfo, game: string): number | undefined {
  return index.latency[player]?.games[`${board.anchor_board}/${game}`]?.median_ms
}

/** Median over a board's games of the per-game median latency. */
export function boardLatency(index: ArenaIndex, player: string, board: BoardInfo): number | undefined {
  const values = board.games
    .map((game) => latencyFor(index, player, board, game))
    .filter((value): value is number => value !== undefined)
    .sort((a, b) => a - b)
  if (values.length === 0) return undefined
  const middle = Math.floor(values.length / 2)
  return values.length % 2 ? values[middle] : ((values[middle - 1] ?? 0) + (values[middle] ?? 0)) / 2
}

/** Reaction delay in steps the real-time board would apply for a latency (one step = 66.7 ms). */
export function delaySteps(latencyMs: number, stepMs = 66.6667): number {
  return Math.max(1, Math.ceil(latencyMs / stepMs))
}

/** Background for a heat cell: the accent mixed into the surface in proportion to k in [0, 1]. */
export function heatBackground(k: number | null | undefined): string | undefined {
  if (k === null || k === undefined || !Number.isFinite(k)) return undefined
  const share = Math.round(6 + Math.min(Math.max(k, 0), 1) * 62)
  return `color-mix(in oklab, var(--heat) ${share}%, var(--surface))`
}

export function replaysOf(index: ArenaIndex, filter: Partial<Pick<ReplayRef, 'board' | 'game' | 'player'>>): ReplayRef[] {
  return index.replays.filter(
    (ref) =>
      (filter.board === undefined || ref.board === filter.board) &&
      (filter.game === undefined || ref.game === filter.game) &&
      (filter.player === undefined || ref.player === filter.player),
  )
}

export function findReplay(index: ArenaIndex, board: string, game: string, player: string, seed: number) {
  return index.replays.find((ref) => ref.board === board && ref.game === game && ref.player === player && ref.seed === seed)
}

/** True when the data is not a published result: dev seeds, or a suite without a lock. */
export function isDevelopmentData(index: ArenaIndex): boolean {
  return index.seed_set !== 'test' || !index.suite.frozen
}
