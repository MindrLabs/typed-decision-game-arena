/**
 * Canvas renderers, one per game, drawing a logged snapshot. Coordinates follow the engines: Tetris and Snake rows
 * from the top, Connect Four rows top to bottom in `grid`, Pong and Breakout in the field coordinates of the text.
 */
import type { BreakoutSnapshot, Cell, Connect4Snapshot, PongSnapshot, SnakeSnapshot, TetrisSnapshot } from '../lib/types'
import type { Palette } from './palette'

export interface Size {
  width: number
  height: number
}

/** Extra marks drawn over a snapshot. */
export interface Overlay {
  /** The band a macro Pong or Breakout decision chose: a y range for Pong, an x range for Breakout. */
  band?: readonly [number, number]
  /** Macro Tetris: where the chosen placement lands. */
  ghost?: readonly Cell[]
  /** Macro Tetris: where another option would land (the one hovered in the side panel). */
  preview?: readonly Cell[]
}

/** The cells a macro Tetris option lands on, when the snapshot carries them. */
export function landingOf(snapshot: unknown, key: string | null | undefined): readonly Cell[] | undefined {
  if (!key || !isTetris(snapshot)) return undefined
  return snapshot.landings?.[key]
}

/** The band a macro decision key ("zone3") selects, in field coordinates (8 bands: 20 pixels in Pong, 18 in
 * Breakout, as in arena/games/pong.py and breakout.py). */
export function bandOf(game: string, choice: string): readonly [number, number] | undefined {
  const match = /^zone(\d+)$/.exec(choice)
  if (!match) return undefined
  const zone = Number(match[1])
  const size = game === 'pong' ? 20 : game === 'breakout' ? 18 : 0
  if (size === 0 || zone < 1 || zone > 8) return undefined
  return [(zone - 1) * size, zone * size - 1]
}

/** Width / height of each game's drawing. */
export const ASPECT: Record<string, number> = {
  tetris: 10 / 20,
  snake: 1,
  connect4: 7 / 6.7,
  pong: 1,
  breakout: 144 / 161,
}

const PIECE_COLOURS: Record<string, string> = {
  I: '#22d3ee',
  O: '#facc15',
  T: '#c084fc',
  S: '#4ade80',
  Z: '#f87171',
  J: '#60a5fa',
  L: '#fb923c',
}

/** Breakout's brick rows, top first, after the Atari palette. */
const BRICK_COLOURS = ['#c84848', '#c66c3a', '#b47a30', '#a2a22a', '#48a048', '#4248c8']

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function isTetris(value: unknown): value is TetrisSnapshot {
  return isObject(value) && Array.isArray(value.board) && isObject(value.piece)
}
export function isSnake(value: unknown): value is SnakeSnapshot {
  return isObject(value) && Array.isArray(value.snake) && typeof value.size === 'number'
}
export function isConnect4(value: unknown): value is Connect4Snapshot {
  return isObject(value) && Array.isArray(value.grid) && typeof value.you === 'string'
}
const isSpanOrNull = (value: unknown): boolean => value === null || Array.isArray(value)
export function isPong(value: unknown): value is PongSnapshot {
  return isObject(value) && Array.isArray(value.score) && isSpanOrNull(value.player) && isSpanOrNull(value.opponent)
}
export function isBreakout(value: unknown): value is BreakoutSnapshot {
  return isObject(value) && Array.isArray(value.bricks) && Array.isArray(value.paddle)
}

/** Occurrences of an ASCII mark in a board line. */
function count(line: string, mark: string): number {
  return line.split(mark).length - 1
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  if (w <= 0 || h <= 0) return
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2)))
  ctx.fill()
}

/** Below this many CSS pixels per cell a board is not worth drawing (a container still being laid out). */
const MIN_CELL = 4

function curtain(ctx: CanvasRenderingContext2D, size: Size, palette: Palette, text: string) {
  ctx.fillStyle = 'rgba(0, 0, 0, 0.55)'
  ctx.fillRect(0, 0, size.width, size.height)
  ctx.fillStyle = palette.text
  ctx.font = `600 ${Math.max(12, Math.round(size.width / 16))}px ui-sans-serif, system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, size.width / 2, size.height / 2)
}

function drawTetris(ctx: CanvasRenderingContext2D, s: TetrisSnapshot, palette: Palette, size: Size, overlay: Overlay) {
  const columns = 10
  const rows = s.board.length || 20
  const cell = Math.floor(Math.min(size.width / columns, size.height / rows))
  if (cell < MIN_CELL) return
  const left = Math.floor((size.width - cell * columns) / 2)
  const top = Math.floor((size.height - cell * rows) / 2)
  ctx.fillStyle = palette.bg
  ctx.fillRect(left, top, cell * columns, cell * rows)
  ctx.strokeStyle = palette.grid
  ctx.lineWidth = 1
  for (let c = 1; c < columns; c++) {
    ctx.beginPath()
    ctx.moveTo(left + c * cell + 0.5, top)
    ctx.lineTo(left + c * cell + 0.5, top + rows * cell)
    ctx.stroke()
  }
  for (let r = 1; r < rows; r++) {
    ctx.beginPath()
    ctx.moveTo(left, top + r * cell + 0.5)
    ctx.lineTo(left + columns * cell, top + r * cell + 0.5)
    ctx.stroke()
  }
  const gap = Math.max(1, Math.round(cell / 12))
  const block = (r: number, c: number, colour: string) => {
    ctx.fillStyle = colour
    roundRect(ctx, left + c * cell + gap, top + r * cell + gap, cell - 2 * gap, cell - 2 * gap, cell / 6)
  }
  s.board.forEach((line, r) => {
    for (let c = 0; c < line.length; c++) if (line[c] === '#') block(r, c, palette.stack)
  })
  const colour = PIECE_COLOURS[s.piece.kind] ?? palette.accent
  if (!s.over) {
    for (const [r, c] of s.piece.cells) block(r, c, colour)
  }
  const outline = (cells: readonly Cell[], stroke: string, dashed: boolean, fill: number) => {
    ctx.save()
    ctx.lineWidth = Math.max(2, Math.round(cell / 9))
    ctx.strokeStyle = stroke
    ctx.setLineDash(dashed ? [Math.max(3, cell / 5), Math.max(2, cell / 8)] : [])
    for (const [r, c] of cells) {
      const x = left + c * cell + gap + ctx.lineWidth / 2
      const y = top + r * cell + gap + ctx.lineWidth / 2
      const w = cell - 2 * gap - ctx.lineWidth
      if (w <= 0) continue
      if (fill > 0) {
        ctx.globalAlpha = fill
        ctx.fillStyle = stroke
        ctx.fillRect(x, y, w, w)
        ctx.globalAlpha = 1
      }
      ctx.strokeRect(x, y, w, w)
    }
    ctx.restore()
  }
  if (overlay.preview && overlay.preview !== overlay.ghost) outline(overlay.preview, palette.text, true, 0)
  if (overlay.ghost) outline(overlay.ghost, colour, false, 0.35)
  if (s.over) curtain(ctx, size, palette, 'topped out')
}

function drawSnake(ctx: CanvasRenderingContext2D, s: SnakeSnapshot, palette: Palette, size: Size) {
  const n = s.size
  const cell = Math.floor(Math.min(size.width, size.height) / n)
  if (cell < MIN_CELL) return
  const left = Math.floor((size.width - cell * n) / 2)
  const top = Math.floor((size.height - cell * n) / 2)
  ctx.fillStyle = palette.bg
  ctx.fillRect(left, top, cell * n, cell * n)
  ctx.fillStyle = palette.grid
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      ctx.fillRect(left + c * cell + cell / 2 - 1, top + r * cell + cell / 2 - 1, 2, 2)
    }
  }
  if (s.food) {
    const [r, c] = s.food
    ctx.fillStyle = palette.food
    ctx.beginPath()
    ctx.arc(left + c * cell + cell / 2, top + r * cell + cell / 2, cell * 0.32, 0, Math.PI * 2)
    ctx.fill()
  }
  const centre = ([r, c]: readonly [number, number]): [number, number] => [left + c * cell + cell / 2, top + r * cell + cell / 2]
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.lineWidth = cell * 0.56
  ctx.strokeStyle = palette.snake
  const length = s.snake.length
  // One path, so the joints do not darken where segments overlap.
  ctx.beginPath()
  s.snake.forEach((segment, i) => {
    const [x, y] = centre(segment)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.globalAlpha = 0.85
  ctx.stroke()
  const tail = s.snake[length - 1]
  if (tail && length > 1) {
    const [tx, ty] = centre(tail)
    ctx.globalAlpha = 0.45
    ctx.fillStyle = palette.snake
    ctx.beginPath()
    ctx.arc(tx, ty, cell * 0.2, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1
  const inset = Math.max(1, Math.round(cell * 0.1))
  const headPosition = s.snake[0]
  if (headPosition) {
    const [r, c] = headPosition
    ctx.fillStyle = palette.snakeHead
    roundRect(ctx, left + c * cell + inset, top + r * cell + inset, cell - 2 * inset, cell - 2 * inset, cell / 4)
  }
  ctx.globalAlpha = 1
  const headCell = s.snake[0]
  if (headCell) {
    const [r, c] = headCell
    const offsets: Record<string, [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }
    const [dx, dy] = offsets[s.heading] ?? [0, -1]
    const cx = left + c * cell + cell / 2
    const cy = top + r * cell + cell / 2
    ctx.fillStyle = palette.bg
    for (const side of [-1, 1]) {
      const ex = cx + dx * cell * 0.18 + (dy !== 0 ? side * cell * 0.17 : 0)
      const ey = cy + dy * cell * 0.18 + (dx !== 0 ? side * cell * 0.17 : 0)
      ctx.beginPath()
      ctx.arc(ex, ey, Math.max(1.5, cell * 0.07), 0, Math.PI * 2)
      ctx.fill()
    }
  }
  if (!s.alive) curtain(ctx, size, palette, 'game over')
}

function drawConnect4(ctx: CanvasRenderingContext2D, s: Connect4Snapshot, palette: Palette, size: Size) {
  const columns = 7
  const rows = s.grid.length || 6
  const cell = Math.floor(Math.min(size.width / columns, size.height / (rows + 0.7)))
  if (cell < MIN_CELL) return
  const left = Math.floor((size.width - cell * columns) / 2)
  const header = Math.round(cell * 0.7)
  const top = Math.floor((size.height - cell * rows - header) / 2) + header
  ctx.fillStyle = palette.dim
  ctx.font = `600 ${Math.max(10, Math.round(cell * 0.32))}px ui-sans-serif, system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (let c = 0; c < columns; c++) {
    ctx.fillStyle = s.last === c + 1 ? palette.accent : palette.dim
    ctx.fillText(String(c + 1), left + c * cell + cell / 2, top - header / 2)
  }
  ctx.fillStyle = palette.board
  roundRect(ctx, left, top, cell * columns, cell * rows, cell * 0.18)
  const lastRow = s.last ? s.grid.findIndex((line) => line[(s.last ?? 1) - 1] !== '.') : -1
  s.grid.forEach((line, r) => {
    for (let c = 0; c < columns; c++) {
      const mark = line[c]
      ctx.fillStyle = mark === 'X' ? palette.x : mark === 'O' ? palette.o : palette.hole
      ctx.beginPath()
      ctx.arc(left + c * cell + cell / 2, top + r * cell + cell / 2, cell * 0.38, 0, Math.PI * 2)
      ctx.fill()
      if (s.last === c + 1 && r === lastRow) {
        ctx.strokeStyle = palette.text
        ctx.lineWidth = Math.max(2, cell * 0.06)
        ctx.beginPath()
        ctx.arc(left + c * cell + cell / 2, top + r * cell + cell / 2, cell * 0.24, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
  })
}

function drawPong(ctx: CanvasRenderingContext2D, s: PongSnapshot, palette: Palette, size: Size, overlay: Overlay) {
  const [fieldW, fieldH] = s.field
  const scale = Math.min(size.width / fieldW, size.height / fieldH)
  const left = (size.width - fieldW * scale) / 2
  const top = (size.height - fieldH * scale) / 2
  const rect = (x: number, y: number, w: number, h: number) => {
    ctx.fillRect(left + x * scale, top + y * scale, w * scale, h * scale)
  }
  ctx.fillStyle = palette.bg
  rect(0, 0, fieldW, fieldH)
  ctx.fillStyle = palette.grid
  for (let y = 2; y < fieldH; y += 10) rect(fieldW / 2 - 0.5, y, 1, 5)
  ctx.font = `600 ${Math.max(12, Math.round(18 * (scale / 2.5)))}px ui-monospace, monospace`
  ctx.textBaseline = 'top'
  ctx.textAlign = 'center'
  ctx.fillStyle = palette.opponent
  ctx.fillText(String(s.score[1]), left + (fieldW / 4) * scale, top + 4 * scale)
  ctx.fillStyle = palette.player
  ctx.fillText(String(s.score[0]), left + (fieldW * 3 / 4) * scale, top + 4 * scale)
  if (overlay.band) {
    ctx.fillStyle = palette.band
    ctx.globalAlpha = 0.28
    rect(134, overlay.band[0], 16, overlay.band[1] - overlay.band[0] + 1)
    ctx.globalAlpha = 1
  }
  const paddle = (x: number, span: [number, number] | null, colour: string) => {
    if (!span) return
    ctx.fillStyle = colour
    rect(x, span[0], 4, span[1] - span[0] + 1)
  }
  paddle(16, s.opponent, palette.opponent)
  paddle(140, s.player, palette.player)
  if (s.ball) {
    ctx.fillStyle = palette.ball
    rect(s.ball[0], s.ball[1], 2, 4)
  }
}

function drawBreakout(ctx: CanvasRenderingContext2D, s: BreakoutSnapshot, palette: Palette, size: Size, overlay: Overlay) {
  const [fieldW, fieldH] = s.field
  const scale = Math.min(size.width / fieldW, size.height / fieldH)
  const left = (size.width - fieldW * scale) / 2
  const top = (size.height - fieldH * scale) / 2
  const rect = (x: number, y: number, w: number, h: number) => {
    ctx.fillRect(left + x * scale, top + y * scale, w * scale, h * scale)
  }
  ctx.fillStyle = palette.bg
  rect(0, 0, fieldW, fieldH)
  ctx.fillStyle = palette.dim
  rect(0, 0, fieldW, 1)
  rect(0, 0, 1, fieldH)
  rect(fieldW - 1, 0, 1, fieldH)
  if (overlay.band) {
    ctx.fillStyle = palette.band
    ctx.globalAlpha = 0.28
    rect(overlay.band[0], 152, overlay.band[1] - overlay.band[0] + 1, 12)
    ctx.globalAlpha = 1
  }
  s.bricks.forEach((line, r) => {
    ctx.fillStyle = BRICK_COLOURS[r] ?? palette.stack
    for (let k = 0; k < line.length; k++) {
      if (line[k] === '#') rect(8 * k + 0.5, 25 + 6 * r + 0.5, 7, 5)
    }
  })
  ctx.fillStyle = palette.paddle
  rect(s.paddle[0], 157, s.paddle[1] - s.paddle[0] + 1, 4)
  if (s.ball) {
    ctx.fillStyle = palette.ball
    rect(s.ball[0], s.ball[1], 2, 4)
  }
  if (s.lives === 0) curtain(ctx, size, palette, 'game over')
}

/** Whether this site knows how to draw `snapshot` for `game`. */
export function canDraw(game: string, snapshot: unknown): boolean {
  switch (game) {
    case 'tetris':
      return isTetris(snapshot)
    case 'snake':
      return isSnake(snapshot)
    case 'connect4':
      return isConnect4(snapshot)
    case 'pong':
      return isPong(snapshot)
    case 'breakout':
      return isBreakout(snapshot)
    default:
      return false
  }
}

/** Draws `snapshot` for `game` (nothing when `canDraw` is false). */
export function drawSnapshot(
  ctx: CanvasRenderingContext2D,
  game: string,
  snapshot: unknown,
  palette: Palette,
  size: Size,
  overlay: Overlay = {},
): void {
  ctx.clearRect(0, 0, size.width, size.height)
  if (game === 'tetris' && isTetris(snapshot)) drawTetris(ctx, snapshot, palette, size, overlay)
  else if (game === 'snake' && isSnake(snapshot)) drawSnake(ctx, snapshot, palette, size)
  else if (game === 'connect4' && isConnect4(snapshot)) drawConnect4(ctx, snapshot, palette, size)
  else if (game === 'pong' && isPong(snapshot)) drawPong(ctx, snapshot, palette, size, overlay)
  else if (game === 'breakout' && isBreakout(snapshot)) drawBreakout(ctx, snapshot, palette, size, overlay)
}

/** One line of text describing a snapshot, for screen readers and the status line. */
export function describeSnapshot(game: string, snapshot: unknown): string {
  if (game === 'tetris' && isTetris(snapshot)) {
    return `${snapshot.lines} lines, ${snapshot.pieces} pieces placed, current ${snapshot.piece.kind}, next ${snapshot.next}${snapshot.over ? ', topped out' : ''}`
  }
  if (game === 'snake' && isSnake(snapshot)) {
    return `${snapshot.eaten} food eaten, length ${snapshot.snake.length}, heading ${snapshot.heading}${snapshot.alive ? '' : ', game over'}`
  }
  if (game === 'connect4' && isConnect4(snapshot)) {
    const last = snapshot.last ? `, last move in column ${snapshot.last}` : ''
    return `playing ${snapshot.you} against ${snapshot.opponent}${last}${snapshot.result ? `, ${snapshot.result}` : ''}`
  }
  if (game === 'pong' && isPong(snapshot)) {
    return `you ${snapshot.score[0]}, opponent ${snapshot.score[1]}${snapshot.ball ? '' : ', no ball in play'}`
  }
  if (game === 'breakout' && isBreakout(snapshot)) {
    const standing = snapshot.bricks.reduce((sum, line) => sum + count(line, '#'), 0)
    return `score ${snapshot.score}, ${snapshot.lives} lives, ${standing} bricks standing`
  }
  return 'unrecognised snapshot'
}
