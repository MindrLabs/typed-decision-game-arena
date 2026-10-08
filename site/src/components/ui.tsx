import type { ReactNode } from 'react'

import { formatInterval, formatNumber } from '../lib/format'
import type { Interval } from '../lib/types'

export function Chip({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'anchor'; title?: string }) {
  const tones = {
    neutral: 'border-line bg-surface-2 text-muted',
    accent: 'border-transparent bg-accent-soft text-accent-strong',
    anchor: 'border-dashed border-faint bg-transparent text-muted',
  }
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full border px-2 py-px text-[11px] leading-4 font-medium whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`min-w-0 rounded-xl border border-line bg-surface ${className}`}>{children}</section>
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-base font-semibold tracking-tight text-fg">{children}</h2>
      {aside ? <div className="text-xs text-muted">{aside}</div> : null}
    </div>
  )
}

/** An estimate and its interval on a fixed axis (0-100 for board indices). */
export function IntervalBar({
  value,
  interval,
  min = 0,
  max = 100,
  label,
}: {
  value: number
  interval: Interval | null | undefined
  min?: number
  max?: number
  label: string
}) {
  const clamp = (x: number) => Math.min(Math.max(x, min), max)
  const position = (x: number) => ((clamp(x) - min) / (max - min)) * 100
  const description = `${label}: ${formatNumber(value, 1)}, interval ${formatInterval(interval, 1)}`
  return (
    <svg viewBox="0 0 100 12" preserveAspectRatio="none" className="h-3 w-28 overflow-visible" role="img" aria-label={description}>
      <title>{description}</title>
      <line x1="0" x2="100" y1="6" y2="6" stroke="var(--border)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {[0, 50, 100].map((tick) => (
        <line key={tick} x1={tick} x2={tick} y1="3" y2="9" stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      {interval ? (
        <line
          x1={position(interval[0])}
          x2={position(interval[1])}
          y1="6"
          y2="6"
          stroke="var(--accent)"
          strokeOpacity="0.55"
          strokeWidth="5"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <line
        x1={position(value)}
        x2={position(value)}
        y1="1"
        y2="11"
        stroke="var(--accent-strong)"
        strokeWidth="2.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1 py-px font-mono text-[0.85em] break-words">{children}</code>
}

export function Command({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-xs leading-relaxed text-fg">
      {children}
    </pre>
  )
}
