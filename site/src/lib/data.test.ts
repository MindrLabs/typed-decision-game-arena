import { gzipSync } from 'node:zlib'

import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeIndex, makeReplay } from '../test/fixtures'
import { DataError, fetchIndex, fetchReplay, parseMaybeGzip } from './data'

function bytes(value: unknown, gzip: boolean): ArrayBuffer {
  const raw = Buffer.from(JSON.stringify(value))
  const data = gzip ? gzipSync(raw) : raw
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength)
}

function respondWith(body: ArrayBuffer, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body, { status }))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('parseMaybeGzip', () => {
  it('inflates gzipped JSON', async () => {
    await expect(parseMaybeGzip(bytes({ hello: 'world', n: [1, 2] }, true))).resolves.toEqual({ hello: 'world', n: [1, 2] })
  })

  it('reads JSON a host already decompressed', async () => {
    await expect(parseMaybeGzip(bytes({ plain: true }, false))).resolves.toEqual({ plain: true })
  })
})

describe('fetchIndex', () => {
  it('loads and checks index.json', async () => {
    const spy = respondWith(bytes(makeIndex(), false))
    const index = await fetchIndex()
    expect(index.suite.id).toBe('v0.1')
    expect(spy).toHaveBeenCalledWith('./data/index.json', expect.objectContaining({ cache: 'no-cache' }))
  })

  it('rejects an unknown schema', async () => {
    respondWith(bytes({ ...makeIndex(), schema: 2 }, false))
    await expect(fetchIndex()).rejects.toThrow(/schema 2/)
  })

  it('reports HTTP errors', async () => {
    respondWith(new ArrayBuffer(0), 404)
    await expect(fetchIndex()).rejects.toBeInstanceOf(DataError)
  })
})

describe('fetchReplay', () => {
  it('loads a gzipped replay', async () => {
    respondWith(bytes(makeReplay(), true))
    const replay = await fetchReplay('replays/macro/tetris/model-a/1001.json.gz')
    expect(replay.decisions).toHaveLength(3)
    expect(replay.decisions[0]?.calls[0]?.p?.['spawn-c8']).toBe(0.7)
  })

  it('rejects something that is not a replay', async () => {
    respondWith(bytes({ schema: 1 }, true))
    await expect(fetchReplay('x.json.gz')).rejects.toThrow(/not a schema 1 replay/)
  })
})
