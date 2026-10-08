import { DevelopmentBanner } from '../components/Layout'
import { IncompleteTable, LeaderboardTable } from '../components/LeaderboardTable'
import { Card, Command, SectionTitle } from '../components/ui'
import { formatCompact, formatInterval, formatNumber, formatP } from '../lib/format'
import { boardTable, findBoard, playerInfo, type BoardTable } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, BoardInfo } from '../lib/types'

function BoardNav({ index, current }: { index: ArenaIndex; current: BoardInfo }) {
  return (
    <nav aria-label="Boards" className="flex flex-wrap gap-1 rounded-lg border border-line bg-surface p-1">
      {index.boards.map((board) => {
        const active = board.id === current.id
        return (
          <a
            key={board.id}
            href={href.board(board.id)}
            aria-current={active ? 'page' : undefined}
            className={`rounded-md px-3 py-1.5 text-sm no-underline transition-colors ${
              active ? 'bg-accent text-white dark:text-[var(--bg)]' : 'text-muted hover:bg-surface-2 hover:text-fg'
            }`}
          >
            {board.title}
          </a>
        )
      })}
    </nav>
  )
}

function Anchors({ index, table }: { index: ArenaIndex; table: BoardTable }) {
  const anchorBoard = findBoard(index, table.board.anchor_board)
  return (
    <p className="text-xs leading-relaxed text-muted">
      Normalised per game: random play = 0, the reference player = 100
      {table.board.anchor_board !== table.board.id ? ` (both from the ${anchorBoard?.title ?? table.board.anchor_board} board)` : ''}.
      Raw anchor means:{' '}
      {table.board.games.map((game, i) => {
        const anchors = table.scores?.anchors[game]
        return (
          <span key={game}>
            {i > 0 ? '; ' : ''}
            {index.games[game]?.title ?? game} {formatCompact(anchors?.random)} / {formatCompact(anchors?.reference)}
          </span>
        )
      })}
      .
    </p>
  )
}

function EmptyBoard({ index, board }: { index: ArenaIndex; board: BoardInfo }) {
  const seedSet = index.seed_set
  const example = 'kev-0.8b'
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold text-fg">No model has finished this board yet</h3>
      <p className="mt-1 text-sm text-muted">
        Every score is placed between two anchors: random play (0) and the reference player (100), each run on the same seeds.
        {board.anchor_board !== board.id
          ? ' The real-time board reuses the frame board’s anchors and needs each model’s latency first.'
          : ''}{' '}
        To add a model:
      </p>
      <div className="mt-3 grid gap-2">
        <Command>{'scripts/serve.sh                         # serve the models (model-compose)'}</Command>
        <Command>
          {board.anchor_board !== board.id
            ? `uv run arena latency --player ${example}       # measure latency alone on the GPU\nuv run arena board --board ${board.id} --player ${example} --seeds ${seedSet}`
            : `uv run arena board --board ${board.id} --player ${example} --seeds ${seedSet}`}
        </Command>
        <Command>{`uv run arena export --seed-set ${seedSet}       # rebuild this site's data`}</Command>
      </div>
    </Card>
  )
}

function Pairs({ index, table }: { index: ArenaIndex; table: BoardTable }) {
  const pairs = table.scores?.pairs ?? []
  if (pairs.length === 0) return null
  const confidence = Math.round(index.suite.confidence * 100)
  return (
    <details className="rounded-xl border border-line bg-surface">
      <summary className="px-4 py-3 text-sm font-medium text-fg">
        Pairwise differences <span className="font-normal text-muted">({pairs.length} pairs, Holm-adjusted)</span>
      </summary>
      <div className="overflow-x-auto border-t border-line">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Index differences between models with paired bootstrap intervals and Holm-adjusted p-values</caption>
          <thead>
            <tr className="border-b border-line bg-surface-2 text-left text-xs text-muted">
              <th scope="col" className="px-3 py-2 font-medium">
                A
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                B
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                A − B
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                {confidence}% interval
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                p (Holm)
              </th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair) => {
              const clear = pair.p_holm < 1 - index.suite.confidence
              return (
                <tr key={`${pair.a}-${pair.b}`} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-1.5">{playerInfo(index, pair.a).title}</td>
                  <td className="px-3 py-1.5">{playerInfo(index, pair.b).title}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">{formatNumber(pair.diff, 1)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums text-muted">{formatInterval(pair.ci, 1)}</td>
                  <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${clear ? 'font-semibold text-good' : 'text-muted'}`}>
                    {formatP(pair.p_holm)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export function LeaderboardView({ index, boardId }: { index: ArenaIndex; boardId: string | null }) {
  const board = findBoard(index, boardId) ?? index.boards[0]
  if (!board) {
    return <p className="text-muted">The exported data has no boards.</p>
  }
  const table = boardTable(index, board)
  const seeds = board.games.map((game) => `${index.games[game]?.title ?? game} ${board.seeds[game] ?? 0}`).join(', ')
  return (
    <div className="flex flex-col gap-5">
      <DevelopmentBanner index={index} />
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Leaderboard</h1>
        <p className="max-w-3xl text-sm text-muted">
          Typed-decision models play five games through one protocol: the same text for every model, seeded option order,
          paired seeds. Each board index runs from 0 (random play) to 100 (a strong rule-based reference).
        </p>
      </div>
      <BoardNav index={index} current={board} />
      <section aria-labelledby="board-title" className="flex flex-col gap-3">
        <SectionTitle aside={`seeds per game: ${seeds}`}>
          <span id="board-title">{board.title} board</span>
        </SectionTitle>
        <p className="-mt-2 max-w-3xl text-sm text-muted">{board.summary}</p>
        {table.scores && table.scores.missing_anchors.length > 0 ? (
          <p role="note" className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-sm text-warn-fg">
            Anchors missing for {table.scores.missing_anchors.join(', ')}: normalised scores cannot be computed there yet.
          </p>
        ) : null}
        {table.ranked.length > 0 ? <LeaderboardTable index={index} table={table} /> : null}
        {!table.hasModels ? <EmptyBoard index={index} board={board} /> : null}
        {table.incomplete.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-fg">Incomplete runs</h3>
            <IncompleteTable index={index} table={table} />
          </div>
        ) : null}
        <Anchors index={index} table={table} />
        <Pairs index={index} table={table} />
      </section>
    </div>
  )
}
