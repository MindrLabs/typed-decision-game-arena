import type { ReactNode } from 'react'

import { formatDate } from '../lib/format'
import { isDevelopmentData } from '../lib/leaderboard'
import { href, type Route } from '../lib/router'
import type { ArenaIndex } from '../lib/types'

function NavLink({ to, current, children }: { to: string; current: boolean; children: ReactNode }) {
  return (
    <a
      href={to}
      aria-current={current ? 'page' : undefined}
      className={`rounded-md px-2.5 py-1 text-sm no-underline transition-colors ${
        current ? 'bg-accent-soft font-medium text-accent-strong' : 'text-muted hover:bg-surface-2 hover:text-fg'
      }`}
    >
      {children}
    </a>
  )
}

export function DevelopmentBanner({ index }: { index: ArenaIndex }) {
  if (!isDevelopmentData(index)) return null
  const reasons = [
    index.seed_set !== 'test' ? `${index.seed_set} seeds` : null,
    index.suite.frozen ? null : `suite ${index.suite.id} not frozen`,
  ].filter(Boolean)
  return (
    <div role="note" className="rounded-lg border border-warn-line bg-warn-bg px-4 py-2.5 text-sm text-warn-fg">
      <strong className="font-semibold">Development data</strong>
      <span> ({reasons.join(', ')}): not a published result. </span>
      <span className="opacity-90">Published numbers come from the test seeds of a frozen suite.</span>
    </div>
  )
}

export function Layout({ index, route, children }: { index: ArenaIndex | null; route: Route; children: ReactNode }) {
  const onLeaderboard = route.name === 'board'
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface/80 backdrop-blur supports-[backdrop-filter]:bg-surface/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <a href={href.home} className="flex items-center gap-2 text-fg no-underline hover:text-fg">
            <svg viewBox="0 0 16 16" className="size-5" aria-hidden="true">
              <rect x="1" y="1" width="6" height="6" rx="1" fill="var(--accent)" />
              <rect x="9" y="1" width="6" height="6" rx="1" fill="var(--heat)" opacity="0.45" />
              <rect x="1" y="9" width="6" height="6" rx="1" fill="var(--heat)" opacity="0.45" />
              <rect x="9" y="9" width="6" height="6" rx="1" fill="var(--accent)" />
            </svg>
            <span className="font-semibold tracking-tight">Typed-Decision Game Arena</span>
          </a>
          <nav aria-label="Main" className="flex items-center gap-1">
            <NavLink to={href.home} current={onLeaderboard}>
              Leaderboard
            </NavLink>
            <NavLink to={href.method} current={route.name === 'method'}>
              Method
            </NavLink>
          </nav>
          {index ? (
            <span className="ml-auto font-mono text-xs text-muted" title={index.suite.lock ? `lock ${index.suite.lock}` : 'suite not frozen'}>
              suite {index.suite.id} · {index.seed_set} seeds
            </span>
          ) : null}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap gap-x-4 gap-y-1 px-4 py-4 text-xs text-faint">
          {index ? (
            <>
              <span>Exported {formatDate(index.generated)}</span>
              <span>arena {index.arena}</span>
              <span className="font-mono">{index.suite.lock ? `lock ${index.suite.lock.slice(0, 16)}…` : 'no lock yet'}</span>
            </>
          ) : null}
          <span className="ml-auto">MIT · MindrLabs</span>
        </div>
      </footer>
    </div>
  )
}
