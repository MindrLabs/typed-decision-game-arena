import { DevelopmentBanner } from '../components/Layout'
import { Card, Chip, Mono, SectionTitle } from '../components/ui'
import { formatCompact, formatDate, formatInterval, formatK, formatMetric, formatMs, formatRate, metricLabel, shortRevision } from '../lib/format'
import { boardTable, latencyFor, playerInfo, replaysOf } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, BiasSummary, BoardInfo, PlayerScore } from '../lib/types'

function Checkpoint({ index, playerId }: { index: ArenaIndex; playerId: string }) {
  const player = playerInfo(index, playerId)
  if (player.kind === 'baseline') {
    return <p className="text-sm text-muted">{player.description}</p>
  }
  const repository = player.repository
  const revision = player.revision
  const link = repository ? `https://huggingface.co/${repository}${revision ? `/tree/${revision}` : ''}` : null
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted">Checkpoint</dt>
      <dd className="min-w-0 break-all">
        {link ? (
          <a href={link} rel="noreferrer" target="_blank">
            {repository}
            <span className="text-muted">@{shortRevision(revision)}</span>
          </a>
        ) : (
          '—'
        )}
      </dd>
      <dt className="text-muted">Family</dt>
      <dd>
        <Mono>{player.family ?? '—'}</Mono>
        {player.preset ? (
          <span className="ml-2 text-muted">
            preset <Mono>{player.preset}</Mono>
          </span>
        ) : null}
      </dd>
      {player.base_model ? (
        <>
          <dt className="text-muted">Base model</dt>
          <dd className="break-all">{player.base_model}</dd>
        </>
      ) : null}
      <dt className="text-muted">Served as</dt>
      <dd>
        model-compose workflow <Mono>{playerId}</Mono>
      </dd>
    </dl>
  )
}

function standing(index: ArenaIndex, board: BoardInfo, playerId: string): string {
  const table = boardTable(index, board)
  const row = table.ranked.find((item) => item.id === playerId)
  if (!row) return ''
  if (row.isAnchor) return ' · anchor'
  const models = table.ranked.filter((item) => !item.isAnchor).length
  return ` · rank ${row.modelRank ?? '?'} of ${models} model${models === 1 ? '' : 's'}`
}

function BoardResults({ index, board, playerId, score }: { index: ArenaIndex; board: BoardInfo; playerId: string; score: PlayerScore }) {
  const confidence = Math.round(index.suite.confidence * 100)
  return (
    <Card className="p-4">
      <SectionTitle
        aside={
          score.index !== undefined ? (
            <span className="font-mono">
              index {formatCompact(score.index, 1)} [{formatInterval(score.index_ci, 1)}]
              {standing(index, board, playerId)}
            </span>
          ) : (
            <span>{score.complete ? 'no index (anchors missing)' : 'incomplete'}</span>
          )
        }
      >
        <a href={href.board(board.id)} className="text-fg no-underline hover:underline">
          {board.title} board
        </a>
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            {board.title} board results per game for {playerInfo(index, playerId).title}
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th scope="col" className="py-1.5 pr-3 font-medium">
                Game
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium whitespace-nowrap">
                Mean ({confidence}% interval)
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                Normalised
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                Seeds
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                Latency
              </th>
              <th scope="col" className="py-1.5 pl-3 font-medium">
                Episode metrics (means; counts for categories)
              </th>
            </tr>
          </thead>
          <tbody>
            {board.games.map((game) => {
              const entry = score.games[game]
              const metrics = Object.entries(entry?.metrics ?? {})
              return (
                <tr key={game} className="border-b border-line align-top last:border-b-0">
                  <th scope="row" className="py-2 pr-3 text-left font-medium text-fg">
                    {index.games[game]?.title ?? game}
                    <div className="text-xs font-normal text-faint">{index.games[game]?.score}</div>
                  </th>
                  <td className="px-3 py-2 text-right font-mono whitespace-nowrap tabular-nums">
                    {formatCompact(entry?.mean)}
                    <div className="text-[11px] text-faint">{formatInterval(entry?.mean_ci, 2)}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono whitespace-nowrap tabular-nums">
                    {formatK(entry?.k)}
                    <div className="text-[11px] text-faint">{formatInterval(entry?.k_ci, 1, 100)}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {entry?.n ?? 0}/{board.seeds[game] ?? 0}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-muted">
                    {formatMs(latencyFor(index, playerId, board, game))}
                  </td>
                  <td className="py-2 pl-3 text-xs text-muted">
                    {metrics.length === 0 ? (
                      '—'
                    ) : (
                      <ul className="flex flex-wrap gap-x-3 gap-y-0.5">
                        {metrics.map(([name, value]) => (
                          <li key={name}>
                            <span className="text-faint">{metricLabel(name)}</span>{' '}
                            <span className="font-mono text-fg">{formatMetric(value)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function BiasRow({ label, summary }: { label: string; summary: BiasSummary }) {
  return (
    <tr className="border-b border-line last:border-b-0">
      <th scope="row" className="py-1.5 pr-3 text-left font-medium">
        {label}
      </th>
      <td className="px-3 py-1.5 text-right font-mono tabular-nums">{summary.n}</td>
      <td className="px-3 py-1.5 text-right font-mono tabular-nums">{formatRate(summary.agreement)}</td>
      <td className="px-3 py-1.5 text-right font-mono tabular-nums">
        {formatRate(summary.first_rate)} <span className="text-faint">vs {formatRate(summary.uniform_rate)}</span>
      </td>
      <td className="px-3 py-1.5 text-right font-mono tabular-nums">
        {formatRate(summary.last_rate)} <span className="text-faint">vs {formatRate(summary.uniform_rate)}</span>
      </td>
    </tr>
  )
}

function Diagnostics({ index, playerId }: { index: ArenaIndex; playerId: string }) {
  const latency = index.latency[playerId]
  const bias = index.bias[playerId]
  if (!latency && !bias) return null
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
      {latency ? (
        <Card className="p-4">
          <SectionTitle aside={`measured ${formatDate(latency.measured)}`}>Latency</SectionTitle>
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Request latency per board and game on fixed probe questions</caption>
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Board / game
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Median
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  p95
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  n
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(latency.games).map(([key, value]) => (
                <tr key={key} className="border-b border-line last:border-b-0">
                  <th scope="row" className="py-1.5 pr-3 text-left font-mono text-xs font-normal">
                    {key}
                  </th>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">{formatMs(value.median_ms)}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted">{formatMs(value.p95_ms)}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted">{value.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-faint">
            {latency.environment.gpu ?? 'unknown GPU'}; {latency.environment.note}.{' '}
            {latency.environment.gpu_processes_at_start.length > 0
              ? `Other GPU processes at start: ${latency.environment.gpu_processes_at_start.join(', ')}.`
              : 'No other GPU processes at start.'}
          </p>
        </Card>
      ) : null}
      {bias ? (
        <Card className="p-4">
          <SectionTitle aside={`measured ${formatDate(bias.measured)}`}>Option-order bias</SectionTitle>
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Agreement between forward and reversed option orders, and position pick rates</caption>
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Game
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  n
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium" title="Same option picked in both orders">
                  Agreement
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  First shown
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Last shown
                </th>
              </tr>
            </thead>
            <tbody>
              <BiasRow label="overall" summary={bias.overall} />
              {Object.entries(bias.games).map(([game, summary]) => (
                <BiasRow key={game} label={index.games[game]?.title ?? game} summary={summary} />
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-faint">
            Each probe question is asked in one order and in reverse. A player that reads the options picks the same option
            both times; position-driven picks show up as first/last rates above the uniform rate.
          </p>
        </Card>
      ) : null}
    </div>
  )
}

function Replays({ index, playerId }: { index: ArenaIndex; playerId: string }) {
  const refs = replaysOf(index, { player: playerId })
  const groups = new Map<string, typeof refs>()
  for (const ref of refs) {
    const key = `${ref.board}/${ref.game}`
    groups.set(key, [...(groups.get(key) ?? []), ref])
  }
  return (
    <Card className="p-4">
      <SectionTitle aside={refs.length > 0 ? `${refs.length} exported` : undefined}>Replays</SectionTitle>
      {refs.length === 0 ? (
        <p className="text-sm text-muted">No replays exported for this player.</p>
      ) : (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-sm">
          {[...groups.entries()].map(([key, items]) => {
            const first = items[0]
            if (!first) return null
            return (
              <div key={key} className="contents">
                <dt className="text-muted">
                  {index.boards.find((b) => b.id === first.board)?.title ?? first.board} · {index.games[first.game]?.title ?? first.game}
                </dt>
                <dd className="flex flex-wrap gap-x-3 gap-y-1">
                  {items.map((ref) => (
                    <a
                      key={ref.path}
                      href={href.replay(ref.board, ref.game, ref.player, ref.seed)}
                      className="whitespace-nowrap"
                      title={`${ref.decisions} decisions`}
                    >
                      seed {ref.seed} <span className="font-mono text-xs text-muted">({formatCompact(ref.score)})</span>
                    </a>
                  ))}
                </dd>
              </div>
            )
          })}
        </dl>
      )}
    </Card>
  )
}

export function ModelView({ index, playerId }: { index: ArenaIndex; playerId: string }) {
  const player = index.players[playerId]
  if (!player) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Unknown player</h1>
        <p className="text-muted">
          No player <Mono>{playerId}</Mono> in the exported data. <a href={href.home}>Back to the leaderboard</a>.
        </p>
      </div>
    )
  }
  const boards = index.boards.filter((board) => index.scores[board.id]?.players[playerId])
  return (
    <div className="flex flex-col gap-5">
      <DevelopmentBanner index={index} />
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-fg">{player.title}</h1>
          {player.kind === 'baseline' ? <Chip tone="anchor">anchor</Chip> : <Chip tone="accent">{player.family ?? 'model'}</Chip>}
        </div>
        {player.kind === 'model' && player.description ? <p className="max-w-3xl text-sm text-muted">{player.description}</p> : null}
        <Checkpoint index={index} playerId={playerId} />
      </div>
      {boards.length === 0 ? (
        <Card className="p-4">
          <p className="text-sm text-muted">No results for this player in the exported data yet.</p>
        </Card>
      ) : (
        boards.map((board) => {
          const score = index.scores[board.id]?.players[playerId]
          return score ? <BoardResults key={board.id} index={index} board={board} playerId={playerId} score={score} /> : null
        })
      )}
      <Diagnostics index={index} playerId={playerId} />
      <Replays index={index} playerId={playerId} />
    </div>
  )
}
