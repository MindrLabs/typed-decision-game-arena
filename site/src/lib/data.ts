import type { ArenaIndex, DuelReplay, Replay, VersusData } from './types'

/** Data lives next to the page (webui/data), so relative URLs work on every static host. */
export const DATA_BASE = './data/'
export const SUPPORTED_SCHEMA = 1

export class DataError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'DataError'
  }
}

function isGzip(bytes: Uint8Array): boolean {
  return bytes.length > 2 && bytes[0] === 0x1f && bytes[1] === 0x8b
}

/** Parse JSON from bytes that may be gzipped. Some hosts decompress `.gz` on the way (Content-Encoding), others
 * hand over the archive itself; the magic bytes tell which. */
export async function parseMaybeGzip<T>(buffer: ArrayBuffer): Promise<T> {
  const bytes = new Uint8Array(buffer)
  if (!isGzip(bytes)) {
    return JSON.parse(new TextDecoder().decode(bytes)) as T
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
  return (await new Response(stream).json()) as T
}

async function fetchBytes(url: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(url, { signal, cache: 'no-cache' })
  if (!response.ok) {
    throw new DataError(`${url}: HTTP ${response.status}`)
  }
  return response.arrayBuffer()
}

function checkIndex(value: unknown): ArenaIndex {
  if (typeof value !== 'object' || value === null) throw new DataError('index.json is not an object')
  const index = value as Partial<ArenaIndex>
  if (index.schema !== SUPPORTED_SCHEMA) {
    throw new DataError(`index.json has schema ${String(index.schema)}; this site reads schema ${SUPPORTED_SCHEMA}`)
  }
  for (const key of ['suite', 'boards', 'games', 'players', 'scores', 'replays'] as const) {
    if (index[key] === undefined) throw new DataError(`index.json has no "${key}"`)
  }
  return { latency: {}, bias: {}, ...index } as ArenaIndex
}

export async function fetchIndex(signal?: AbortSignal): Promise<ArenaIndex> {
  const buffer = await fetchBytes(`${DATA_BASE}index.json`, signal)
  return checkIndex(await parseMaybeGzip<unknown>(buffer))
}

export async function fetchReplay(path: string, signal?: AbortSignal): Promise<Replay> {
  const replay = await parseMaybeGzip<Replay>(await fetchBytes(`${DATA_BASE}${path}`, signal))
  if (replay.schema !== SUPPORTED_SCHEMA || !Array.isArray(replay.decisions)) {
    throw new DataError(`${path}: not a schema ${SUPPORTED_SCHEMA} replay`)
  }
  return replay
}

export async function fetchVersus(signal?: AbortSignal): Promise<VersusData> {
  const data = await parseMaybeGzip<VersusData>(await fetchBytes(`${DATA_BASE}versus.json`, signal))
  if (data.schema !== SUPPORTED_SCHEMA || !Array.isArray(data.games)) {
    throw new DataError(`versus.json is not schema ${SUPPORTED_SCHEMA} versus data`)
  }
  return data
}

export async function fetchDuel(path: string, signal?: AbortSignal): Promise<DuelReplay> {
  const replay = await parseMaybeGzip<DuelReplay>(await fetchBytes(`${DATA_BASE}${path}`, signal))
  if (replay.schema !== SUPPORTED_SCHEMA || !Array.isArray(replay.decisions)) {
    throw new DataError(`${path}: not a schema ${SUPPORTED_SCHEMA} direct game`)
  }
  return replay
}

// Promise caches for React's `use`: one request per resource for the lifetime of the page.
let indexPromise: Promise<ArenaIndex> | null = null
const replayPromises = new Map<string, Promise<Replay>>()

let versusPromise: Promise<VersusData> | null = null
const duelPromises = new Map<string, Promise<DuelReplay>>()

export function versusResource(): Promise<VersusData> {
  if (!versusPromise) {
    const promise = fetchVersus()
    versusPromise = promise
    promise.catch(() => {
      versusPromise = null
    })
  }
  return versusPromise
}

export function duelResource(path: string): Promise<DuelReplay> {
  let promise = duelPromises.get(path)
  if (!promise) {
    promise = fetchDuel(path)
    duelPromises.set(path, promise)
    promise.catch(() => duelPromises.delete(path))
  }
  return promise
}

/** Where `arena export` writes the replay of a run and of a direct game. */
export function replayPath(board: string, game: string, player: string, seed: number): string {
  return `replays/${board}/${game}/${player}/${seed}.json.gz`
}

export function duelPath(pair: string, seed: number, gameNo: number): string {
  return `replays/duel/${pair}/${seed}-${gameNo}.json.gz`
}

export function indexResource(): Promise<ArenaIndex> {
  indexPromise ??= fetchIndex()
  return indexPromise
}

export function replayResource(path: string): Promise<Replay> {
  let promise = replayPromises.get(path)
  if (!promise) {
    promise = fetchReplay(path)
    replayPromises.set(path, promise)
    // A failed fetch should be retried on the next visit, not cached forever.
    promise.catch(() => replayPromises.delete(path))
  }
  return promise
}
