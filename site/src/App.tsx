import { Suspense, use, useEffect } from 'react'

import { ErrorBoundary } from './components/ErrorBoundary'
import { Layout } from './components/Layout'
import { Card, Command } from './components/ui'
import { indexResource } from './lib/data'
import { findBoard, playerInfo } from './lib/leaderboard'
import { href, useRoute, type Route } from './lib/router'
import type { ArenaIndex } from './lib/types'
import { LeaderboardView } from './pages/LeaderboardPage'
import { MethodView } from './pages/MethodPage'
import { ModelView } from './pages/ModelPage'
import { ReplayPage } from './pages/ReplayPage'

const SITE = 'Typed-Decision Game Arena'

function title(index: ArenaIndex, route: Route): string {
  switch (route.name) {
    case 'board': {
      const board = findBoard(index, route.board) ?? index.boards[0]
      return board ? `${board.title} board · ${SITE}` : SITE
    }
    case 'model':
      return `${playerInfo(index, route.player).title} · ${SITE}`
    case 'replay':
      return `${index.games[route.game]?.title ?? route.game} replay · ${playerInfo(index, route.player).title} · ${SITE}`
    case 'method':
      return `Method · ${SITE}`
    case 'notfound':
      return `Not found · ${SITE}`
  }
}

function Page({ index, route }: { index: ArenaIndex; route: Route }) {
  switch (route.name) {
    case 'board':
      return <LeaderboardView index={index} boardId={route.board} />
    case 'model':
      return <ModelView index={index} playerId={route.player} />
    case 'replay':
      return <ReplayPage index={index} board={route.board} game={route.game} player={route.player} seed={route.seed} />
    case 'method':
      return <MethodView index={index} />
    case 'notfound':
      return (
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Not found</h1>
          <p className="text-sm text-muted">
            Nothing at <code className="font-mono">#/{route.path}</code>. <a href={href.home}>Back to the leaderboard</a>.
          </p>
        </div>
      )
  }
}

function Routed({ route }: { route: Route }) {
  const index = use(indexResource())
  const pageTitle = title(index, route)
  const page = window.location.hash
  useEffect(() => {
    document.title = pageTitle
  }, [pageTitle])
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [page])
  return (
    <Layout index={index} route={route}>
      <Page index={index} route={route} />
    </Layout>
  )
}

function LoadError({ error }: { error: Error }) {
  return (
    <Card className="p-5">
      <h1 className="text-lg font-semibold text-fg">The leaderboard data could not be loaded</h1>
      <p className="mt-1 font-mono text-xs text-muted">{error.message}</p>
      <p className="mt-3 text-sm text-muted">
        The site reads <code className="font-mono">data/index.json</code> next to this page. Write it from the repository with:
      </p>
      <div className="mt-2">
        <Command>{'uv run arena export --seed-set test     # or --seed-set dev for development data'}</Command>
      </div>
    </Card>
  )
}

export function App() {
  const route = useRoute()
  return (
    <ErrorBoundary
      fallback={(error) => (
        <Layout index={null} route={route}>
          <LoadError error={error} />
        </Layout>
      )}
    >
      <Suspense
        fallback={
          <Layout index={null} route={route}>
            <p className="text-sm text-muted" role="status">
              Loading…
            </p>
          </Layout>
        }
      >
        <Routed route={route} />
      </Suspense>
    </ErrorBoundary>
  )
}
