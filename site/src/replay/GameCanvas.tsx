import { useEffect, useRef, useState } from 'react'

import type { Cell } from '../lib/types'
import { usePalette } from './palette'
import { ASPECT, canDraw, drawSnapshot, type Candidate, type Size } from './renderers'

const MAX_HEIGHT = 520

function fit(width: number, aspect: number): Size {
  const height = Math.min(width / aspect, MAX_HEIGHT)
  return { width: Math.floor(Math.min(width, height * aspect)), height: Math.floor(height) }
}

/** A crisp (device-pixel-ratio aware) canvas sized to its container, drawing one snapshot. */
export function GameCanvas({
  game,
  snapshot,
  label,
  band,
  ghost,
  preview,
  candidates,
  candidateColour,
}: {
  game: string
  snapshot: unknown
  label: string
  band?: readonly [number, number] | undefined
  /** Cells of the chosen landing (macro Tetris), taken from the snapshot so the reference stays stable. */
  ghost?: readonly Cell[] | undefined
  /** Cells of a hovered option's landing (macro Tetris). */
  preview?: readonly Cell[] | undefined
  /** Versus: the likeliest options, numbered, in `candidateColour`. */
  candidates?: readonly Candidate[] | undefined
  candidateColour?: string | undefined
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const palette = usePalette()
  const [available, setAvailable] = useState(0)
  const { width, height } = fit(available, ASPECT[game] ?? 1)
  const drawable = canDraw(game, snapshot)
  const bandLow = band?.[0]
  const bandHigh = band?.[1]

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setAvailable(Math.floor(entry.contentRect.width))
    })
    observer.observe(element)
    return () => {
      observer.disconnect()
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || width <= 0 || height <= 0) return
    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    ctx.imageSmoothingEnabled = false
    const overlay = {
      ...(bandLow !== undefined && bandHigh !== undefined ? { band: [bandLow, bandHigh] as const } : {}),
      ...(ghost ? { ghost } : {}),
      ...(preview ? { preview } : {}),
      ...(candidates ? { candidates } : {}),
      ...(candidateColour ? { candidateColour } : {}),
    }
    drawSnapshot(ctx, game, snapshot, palette, { width, height }, overlay)
  }, [game, snapshot, palette, width, height, bandLow, bandHigh, ghost, preview, candidates, candidateColour])

  return (
    <div ref={containerRef} className="flex w-full flex-col items-center">
      {drawable ? (
        <canvas ref={canvasRef} role="img" aria-label={label} style={{ width, height }} className="rounded-lg" />
      ) : (
        <p className="py-8 text-sm text-muted">This snapshot cannot be drawn.</p>
      )}
    </div>
  )
}
