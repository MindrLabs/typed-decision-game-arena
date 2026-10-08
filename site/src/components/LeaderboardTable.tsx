import { formatCompact, formatInterval, formatK, formatMs, formatNumber } from '../lib/format'
import { boardLatency, heatBackground, latencyFor, replaysOf, type BoardTable, type Row } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex } from '../lib/types'
import { Chip, IntervalBar } from './ui'

function gameTooltip(index: ArenaIndex, table: BoardTable, row: Row, game: string): string {
  const title = index.games[game]?.title ?? game
  const entry = row.score.games[game]
  const anchors = table.scores?.anchors[game]
  const lines = [`${title} (${index.games[game]?.score ?? 'score'})`]
  if (entry?.mean !== undefined) lines.push(`mean ${formatCompact(entry.mean)} (interval ${formatInterval(entry.mean_ci, 2)}), ${entry.n} seeds`)
  if (entry?.k !== undefined && entry.k !== null) lines.push(`normalised ${formatK(entry.k)} (interval ${formatInterval(entry.k_ci, 1, 100)})`)
  if (anchors) lines.push(`anchors: random ${formatCompact(anchors.random)}, reference ${formatCompact(anchors.reference)}`)
  const latency = latencyFor(index, row.id, table.board, game)
  if (latency !== undefined) lines.push(`median latency ${formatMs(latency)}`)
  return lines.join('\n')
}

function PlayerCell({ row }: { row: Row }) {
  return (
    <div className="flex min-w-44 flex-wrap items-center gap-x-2 gap-y-0.5">
      <a href={href.model(row.id)} className="font-medium text-fg no-underline hover:underline">
        {row.player.title}
      </a>
      {row.isAnchor ? (
        <Chip tone="anchor" title={row.player.description}>
          anchor
        </Chip>
      ) : row.player.family ? (
        <Chip>{row.player.family}</Chip>
      ) : null}
    </div>
  )
}

function ReplayLinks({ index, table, row }: { index: ArenaIndex; table: BoardTable; row: Row }) {
  const refs = table.board.games.flatMap((game) => replaysOf(index, { board: table.board.id, game, player: row.id }).slice(0, 1))
  if (refs.length === 0) return <span className="text-faint">—</span>
  return (
    <div className="flex gap-1">
      {refs.map((ref) => (
        <a
          key={ref.path}
          href={href.replay(ref.board, ref.game, ref.player, ref.seed)}
          className="rounded border border-line px-1.5 py-px font-mono text-[11px] no-underline hover:border-accent"
          title={`${index.games[ref.game]?.title ?? ref.game} replay, seed ${ref.seed}`}
          aria-label={`${row.player.title}: ${index.games[ref.game]?.title ?? ref.game} replay, seed ${ref.seed}`}
        >
          {(index.games[ref.game]?.title ?? ref.game).slice(0, 2)}
        </a>
      ))}
    </div>
  )
}

export function LeaderboardTable({ index, table }: { index: ArenaIndex; table: BoardTable }) {
  const { board } = table
  const confidence = Math.round(index.suite.confidence * 100)
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          {board.title} board: index from 0 (random play) to 100 (reference player), with {confidence}% intervals, and the
          normalised score per game
        </caption>
        <thead>
          <tr className="border-b border-line bg-surface-2 text-left text-xs text-muted">
            <th scope="col" className="w-10 px-3 py-2 font-medium">
              #
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Player
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Index <span className="font-normal text-faint">({confidence}% interval)</span>
            </th>
            {board.games.map((game) => (
              <th key={game} scope="col" className="px-2 py-2 text-right font-medium" title={index.games[game]?.score}>
                {index.games[game]?.title ?? game}
              </th>
            ))}
            <th scope="col" className="px-3 py-2 text-right font-medium" title="Median over this board's games of the median latency per request">
              Latency
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Replays
            </th>
          </tr>
        </thead>
        <tbody>
          {table.ranked.map((row) => {
            const latency = boardLatency(index, row.id, board)
            return (
              <tr
                key={row.id}
                className={`border-b border-line last:border-b-0 ${row.isAnchor ? 'bg-[repeating-linear-gradient(135deg,transparent_0_6px,var(--surface-2)_6px_12px)] text-muted' : ''}`}
              >
                <td className="px-3 py-2 font-mono text-xs tabular-nums text-muted">{row.modelRank ?? '·'}</td>
                <td className="px-3 py-2">
                  <PlayerCell row={row} />
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="w-12 text-right font-mono text-base font-semibold tabular-nums text-fg">
                      {formatNumber(row.score.index, 1)}
                    </span>
                    <div className="flex flex-col gap-0.5">
                      <IntervalBar value={row.score.index ?? 0} interval={row.score.index_ci} label={`${row.player.title} index`} />
                      <span className="font-mono text-[11px] tabular-nums text-faint">{formatInterval(row.score.index_ci, 1)}</span>
                    </div>
                  </div>
                </td>
                {board.games.map((game) => {
                  const entry = row.score.games[game]
                  return (
                    <td
                      key={game}
                      className="px-2 py-2 text-right font-mono tabular-nums"
                      style={{ background: heatBackground(entry?.k) }}
                      title={gameTooltip(index, table, row, game)}
                    >
                      {formatK(entry?.k)}
                    </td>
                  )
                })}
                <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-muted">{formatMs(latency)}</td>
                <td className="px-3 py-2">
                  <ReplayLinks index={index} table={table} row={row} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function IncompleteTable({ index, table }: { index: ArenaIndex; table: BoardTable }) {
  if (table.incomplete.length === 0) return null
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Players whose runs do not cover every game and seed of this board yet</caption>
        <thead>
          <tr className="border-b border-line bg-surface-2 text-left text-xs text-muted">
            <th scope="col" className="px-3 py-2 font-medium">
              Player
            </th>
            {table.board.games.map((game) => (
              <th key={game} scope="col" className="px-2 py-2 text-right font-medium">
                {index.games[game]?.title ?? game}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.incomplete.map((row) => (
            <tr key={row.id} className="border-b border-line last:border-b-0">
              <td className="px-3 py-2">
                <PlayerCell row={row} />
              </td>
              {table.board.games.map((game) => {
                const done = row.score.games[game]?.n ?? 0
                const total = table.board.seeds[game] ?? 0
                return (
                  <td key={game} className="px-2 py-2 text-right font-mono text-xs tabular-nums text-muted">
                    {done}/{total} seeds
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
