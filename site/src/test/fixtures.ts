import type { ArenaIndex, Replay } from '../lib/types'

/** A small index with two models (one complete, one not), both anchors, latency, a pair and replays. */
export function makeIndex(overrides: Partial<ArenaIndex> = {}): ArenaIndex {
  return {
    schema: 1,
    arena: '0.1.0',
    generated: '2026-10-08T00:00:00+00:00',
    suite: { id: 'v0.1', frozen: false, lock: null, group_size: 8, bootstrap: 2000, confidence: 0.95, sticky: 0.25 },
    seed_set: 'dev',
    boards: [
      { id: 'macro', title: 'Macro', summary: 'Turn-based macro decisions.', games: ['tetris', 'pong'], anchor_board: 'macro', seeds: { tetris: 2, pong: 2 } },
      { id: 'frame', title: 'Frame', summary: 'One decision per step.', games: ['tetris'], anchor_board: 'frame', seeds: { tetris: 2 } },
      { id: 'realtime', title: 'Real-time', summary: 'With reaction time.', games: ['tetris'], anchor_board: 'frame', seeds: { tetris: 2 } },
    ],
    games: {
      tetris: { title: 'Tetris', score: 'lines cleared' },
      pong: { title: 'Pong', score: 'points won minus points lost' },
    },
    players: {
      random: { title: 'Random', kind: 'baseline', description: 'Uniformly random.' },
      reference: { title: 'Reference', kind: 'baseline', description: 'Rule-based.' },
      'model-a': {
        title: 'Model A',
        kind: 'model',
        description: 'A test model.',
        family: 'kev',
        repository: 'org/model-a',
        revision: '0123456789abcdef0123',
        base_model: null,
        preset: null,
      },
      'model-b': { title: 'Model B', kind: 'model', description: 'Unfinished.', family: 'laya', repository: 'org/model-b', revision: null },
    },
    scores: {
      macro: {
        board: 'macro',
        anchor_board: 'macro',
        games: ['tetris', 'pong'],
        anchors: { tetris: { n: 2, random: 0, reference: 100 }, pong: { n: 2, random: -20, reference: 0 } },
        missing_anchors: [],
        players: {
          reference: {
            complete: true,
            games: {
              tetris: { n: 2, mean: 100, mean_ci: [98, 102], k: 1, k_ci: [1, 1] },
              pong: { n: 2, mean: 0, mean_ci: [-1, 1], k: 1, k_ci: [1, 1] },
            },
            index: 100,
            index_ci: [100, 100],
            rank: 1,
          },
          'model-a': {
            complete: true,
            games: {
              tetris: { n: 2, mean: 40, mean_ci: [30, 50], k: 0.4, k_ci: [0.3, 0.5], metrics: { lines: 40, topped_out: 0.5 } },
              pong: { n: 2, mean: -10, mean_ci: [-12, -8], k: 0.5, k_ci: [0.4, 0.6], metrics: { result: { win: 1, loss: 1 } } },
            },
            index: 45,
            index_ci: [37.5, 52.5],
            rank: 2,
          },
          random: {
            complete: true,
            games: {
              tetris: { n: 2, mean: 0, mean_ci: [0, 0], k: 0, k_ci: [0, 0] },
              pong: { n: 2, mean: -20, mean_ci: [-21, -19], k: 0, k_ci: [0, 0] },
            },
            index: 0,
            index_ci: [0, 0],
            rank: 3,
          },
          'model-b': { complete: false, games: { tetris: { n: 1, mean: 3 }, pong: { n: 0 } } },
        },
        ranking: ['reference', 'model-a', 'random'],
        pairs: [{ a: 'model-a', b: 'model-c', diff: 12.5, ci: [4, 21], p: 0.004, p_holm: 0.008 }],
      },
      frame: {
        board: 'frame',
        anchor_board: 'frame',
        games: ['tetris'],
        anchors: { tetris: { n: 2, random: 0, reference: 40 } },
        missing_anchors: [],
        players: {},
        ranking: [],
        pairs: [],
      },
      realtime: {
        board: 'realtime',
        anchor_board: 'frame',
        games: ['tetris'],
        anchors: { tetris: { n: 2, random: 0, reference: 40 } },
        missing_anchors: [],
        players: {},
        ranking: [],
        pairs: [],
      },
    },
    latency: {
      'model-a': {
        suite: 'v0.1',
        player: 'model-a',
        measured: '2026-10-08T00:00:00+00:00',
        server: 'http://127.0.0.1:8380/api',
        warmup: 20,
        games: {
          'macro/tetris': { n: 200, median_ms: 40, p95_ms: 60, mean_ms: 42 },
          'macro/pong': { n: 200, median_ms: 30, p95_ms: 50, mean_ms: 33 },
          'frame/tetris': { n: 200, median_ms: 150, p95_ms: 200, mean_ms: 155 },
        },
        environment: { gpu: 'NVIDIA GB10', gpu_processes_at_start: [], machine: 'aarch64', note: 'client-side wall time' },
      },
    },
    bias: {},
    replays: [
      { board: 'macro', game: 'tetris', player: 'model-a', seed: 1001, score: 41, decisions: 3, path: 'replays/macro/tetris/model-a/1001.json.gz' },
      { board: 'macro', game: 'pong', player: 'model-a', seed: 1001, score: -9, decisions: 3, path: 'replays/macro/pong/model-a/1001.json.gz' },
    ],
    ...overrides,
  }
}

const emptyBoard = Array.from({ length: 20 }, () => '..........')

/** Where each fixture option lands (rows from the top, as the engine writes them). */
export const LANDINGS: Record<string, [number, number][]> = {
  'spawn-c1': [[18, 1], [19, 0], [19, 1], [19, 2]],
  'cw-c2': [[17, 1], [18, 1], [18, 2], [19, 1]],
  'spawn-c8': [[18, 8], [19, 7], [19, 8], [19, 9]],
}

/** A three-decision macro Tetris replay with requests, probabilities, landings and the final position. */
export function makeReplay(overrides: Partial<Replay> = {}): Replay {
  const snapshot = (lines: number) => ({
    board: emptyBoard,
    piece: { kind: 'T', cells: [[0, 4], [1, 3], [1, 4], [1, 5]] },
    next: 'S',
    lines,
    pieces: lines,
    over: false,
    landings: LANDINGS,
  })
  const options = [
    { key: 'spawn-c1', text: 'rotation spawn, lands in columns 1-3, rows 1-2: clears 0 lines; holes after: 0; stack height after: 2' },
    { key: 'cw-c2', text: 'rotation cw, lands in columns 2-3, rows 1-3: clears 0 lines; holes after: 0; stack height after: 3' },
    { key: 'spawn-c8', text: 'rotation spawn, lands in columns 8-10, rows 1-2: clears 0 lines; holes after: 0; stack height after: 2' },
  ]
  return {
    schema: 1,
    board: 'macro',
    game: 'tetris',
    player: 'model-a',
    seed: 1001,
    score: 41,
    metrics: { lines: 41, pieces: 3, topped_out: false },
    delay_steps: 0,
    decisions: [0, 1, 2].map((i) => ({
      i,
      step: i,
      snapshot: snapshot(i),
      state: `Tetris state ${i}`,
      instructions: 'Choose where the current piece lands.',
      options,
      calls: [{ stage: 'single', keys: ['cw-c2', 'spawn-c8', 'spawn-c1'], choice: 'spawn-c8', p: { 'cw-c2': 0.2, 'spawn-c8': 0.7, 'spawn-c1': 0.1 }, ms: 41.5 }],
      choice: 'spawn-c8',
      forced: false,
    })),
    final: {
      final: true,
      step: 3,
      snapshot: { board: [...emptyBoard.slice(0, 18), '.......#..', '......####'], piece: { kind: 'S', cells: [[0, 4]] }, next: 'Z', lines: 41, pieces: 3, over: true },
    },
    ...overrides,
  }
}
