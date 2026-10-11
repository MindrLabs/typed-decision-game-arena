/**
 * The data contract with `arena export` (arena/export.py, arena/score.py): webui/data/index.json and the gzipped
 * replays next to it. Field names stay snake_case to match the JSON exactly.
 */

export type Interval = readonly [number, number]

export interface SuiteInfo {
  id: string
  frozen: boolean
  lock: string | null
  group_size: number
  bootstrap: number
  confidence: number
  sticky: number
}

export interface BoardInfo {
  id: string
  title: string
  summary: string
  games: string[]
  /** Board whose random/reference runs anchor this one (the real-time board uses the frame board). */
  anchor_board: string
  seeds: Record<string, number>
}

export interface GameInfo {
  title: string
  score: string
}

export interface PlayerInfo {
  title: string
  kind: 'model' | 'baseline'
  description: string
  family?: string | null
  repository?: string | null
  revision?: string | null
  base_model?: string | null
  preset?: string | null
}

/** Numeric metrics are means over episodes (booleans as rates); categorical ones are counts per value. */
export type MetricValue = number | Record<string, number>

export interface GameScore {
  n: number
  mean?: number
  mean_ci?: Interval | null
  k?: number | null
  k_ci?: Interval | null
  metrics?: Record<string, MetricValue>
  latency_ms?: { median_of_episode_medians: number; episodes: number }
}

export interface PlayerScore {
  complete: boolean
  games: Record<string, GameScore>
  index?: number
  index_ci?: Interval | null
  rank?: number
}

export interface Pair {
  a: string
  b: string
  diff: number
  ci: Interval | null
  p: number
  p_holm: number
}

export interface AnchorScores {
  n: number
  random?: number
  reference?: number
}

export interface BoardScores {
  board: string
  anchor_board: string
  games: string[]
  anchors: Record<string, AnchorScores>
  missing_anchors: string[]
  players: Record<string, PlayerScore>
  ranking: string[]
  pairs: Pair[]
}

export interface LatencyGame {
  n: number
  median_ms: number
  p95_ms: number
  mean_ms: number
}

export interface LatencyFile {
  suite: string
  player: string
  measured: string
  server: string
  warmup: number
  /** Keyed "<board>/<game>" for the macro and frame boards. */
  games: Record<string, LatencyGame>
  environment: {
    gpu: string | null
    gpu_processes_at_start: string[]
    machine: string
    note: string
  }
}

export interface BiasSummary {
  n: number
  agreement?: number
  first_rate?: number
  last_rate?: number
  uniform_rate?: number
}

export interface BiasFile {
  suite: string
  player: string
  measured: string
  games: Record<string, BiasSummary>
  overall: BiasSummary
}

export interface ReplayRef {
  board: string
  game: string
  player: string
  seed: number
  score: number
  decisions: number
  path: string
}

export interface ArenaIndex {
  schema: number
  arena: string
  generated: string
  suite: SuiteInfo
  seed_set: string
  boards: BoardInfo[]
  games: Record<string, GameInfo>
  players: Record<string, PlayerInfo>
  scores: Record<string, BoardScores>
  latency: Record<string, LatencyFile>
  bias: Record<string, BiasFile>
  replays: ReplayRef[]
}

// --- replays -------------------------------------------------------------------------------------------------

export interface ReplayOption {
  key: string
  text: string
}

export interface ReplayCall {
  stage: string
  /** Options in the order they were shown. */
  keys: string[]
  choice: string
  p: Record<string, number> | null
  ms: number
}

export interface ReplayDecision {
  i: number
  step: number
  snapshot: unknown
  state: string
  instructions: string
  /** Options in the engine's canonical order. */
  options: ReplayOption[]
  calls: ReplayCall[]
  choice: string
  forced: boolean
}

/** The position after the last move (optional: older exports do not have it). */
export interface ReplayFinal {
  final: true
  step: number
  snapshot: unknown
}

export interface Replay {
  schema: number
  board: string
  game: string
  player: string
  seed: number
  score: number
  metrics: Record<string, unknown>
  delay_steps: number
  decisions: ReplayDecision[]
  final?: ReplayFinal | null
}

export type Cell = [number, number]

export interface TetrisSnapshot {
  /** 20 rows, top to bottom, '#' filled and '.' empty. */
  board: string[]
  piece: { kind: string; cells: Cell[] }
  next: string
  lines: number
  pieces: number
  over: boolean
  /** Macro board only: the four cells each option's placement lands on, by option key. */
  landings?: Record<string, Cell[]>
}

export interface SnakeSnapshot {
  size: number
  /** Head first, (row, column) from the top-left. */
  snake: Cell[]
  food: Cell | null
  heading: string
  eaten: number
  alive: boolean
}

export interface Connect4Snapshot {
  /** 6 rows, top to bottom, 'X' (moves first), 'O' or '.'. */
  grid: string[]
  you: 'X' | 'O'
  opponent: string
  /** 1-based column of the last move. */
  last: number | null
  result: string | null
}

export interface PongSnapshot {
  field: [number, number]
  /** Top-left corner of the 2 x 4 ball. */
  ball: Cell | null
  /** Vertical span of the player's paddle at x 140-143; null while it is off the field. */
  player: [number, number] | null
  /** Vertical span of the opponent's paddle at x 16-19; null while it is off the field (the first steps of a game). */
  opponent: [number, number] | null
  score: [number, number]
}

export interface BreakoutSnapshot {
  field: [number, number]
  ball: Cell | null
  paddle: [number, number]
  lives: number
  score: number
  /** 6 rows of 18, top row first, '#' standing and '.' broken. */
  bricks: string[]
}

// --- versus (webui/data/versus.json, arena/versus.py) ---------------------------------------------------------

/** How two runs of one seed line up: by decision (turn-based boards) or by game step (real-time board). */
export type SyncUnit = 'decision' | 'step'

export interface VersusGame {
  board: string
  game: string
  sync: SyncUnit
  /** What one position is called: "piece", "step", "decision", "frame". */
  unit: string
  seeds: number[]
}

export interface VersusExcluded {
  board: string
  game: string
  reason: string
}

/** [score, length in sync units, how the run ended] */
export type VersusEpisode = [number, number | null, string]

/** [lead changes, chase (0 or 1), margin first - second] for the pair in sorted order. */
export type VersusMatchRow = [number, number, number]

export interface VersusPick {
  board: string
  game: string
  a: string
  b: string
  seed: number
  lead_changes: number
  chase: boolean
  margin: number
}

export interface LatencySummary {
  median: number
  p95: number
  n: number
}

export interface DuelGameRow {
  seed: number
  game_no: number
  x: string
  o: string
  result: 'X' | 'O' | 'draw' | 'unfinished'
  moves: number
  missed_wins: Record<string, number>
  allowed_wins: Record<string, number>
  latency_ms: Record<string, LatencySummary | null>
}

export interface DuelRating {
  elo: number
  interval: [number, number] | null
  games: number
  points: number
  missed_wins: number
  allowed_wins: number
}

export interface DuelPairScore {
  games: number
  points: Record<string, number>
  wins: Record<string, number>
  draws: number
  openings: Record<string, Record<string, number>>
}

export interface DuelSection {
  suite: string
  seed_set: string
  /** 1-based columns of X's and O's first moves, by seed. */
  openings: Record<string, [number, number]>
  /** Games by pair id "a~b" (sorted). */
  games: Record<string, DuelGameRow[]>
  ratings: Record<string, DuelRating>
  pairs: Record<string, DuelPairScore>
}

export interface VersusData {
  schema: number
  suite: string
  seed_set: string
  models: string[]
  games: VersusGame[]
  excluded: VersusExcluded[]
  /** "<board>/<game>" -> model -> seed -> episode */
  episodes: Record<string, Record<string, Record<string, VersusEpisode>>>
  /** "<board>/<game>" -> pair id -> seed -> row */
  matches: Record<string, Record<string, Record<string, VersusMatchRow>>>
  /** The reference player's score on the seed. */
  par: Record<string, Record<string, number>>
  /** Real-time board: each model's reaction delay in steps. */
  delays: Record<string, Record<string, number>>
  /** The lowest final score any model reached on the game (every point lost, no line cleared). */
  floors: Record<string, number>
  picks: VersusPick[]
  duel: DuelSection | null
}

export interface DuelSnapshot {
  grid: string[]
  to_move: 'X' | 'O'
  last: number | null
  moves: number
  result: string | null
}

export interface DuelDecision extends ReplayDecision {
  side: 'X' | 'O'
  player: string
}

export interface DuelReplay {
  schema: number
  pair: string
  seed: number
  game_no: number
  x: string
  o: string
  opening: [number, number]
  result: string
  decisions: DuelDecision[]
  final: ReplayFinal | null
}
