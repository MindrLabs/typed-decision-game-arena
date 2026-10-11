import { use } from 'react'

import { Card } from '../components/ui'
import { versusResource } from '../lib/data'
import { formatNumber } from '../lib/format'
import { playerInfo } from '../lib/leaderboard'
import { href } from '../lib/router'
import type { ArenaIndex, VersusData } from '../lib/types'
import { formatScore, pairId, seedRows, seriesRecord, splitPair, whyWatch, type SeedRow } from '../lib/versus'
import { TEAM, TeamDot } from './parts'

const DIRECT = 'direct'

interface Selection {
  board: string
  game: string
  a: string
  b: string
}

function defaults(data: VersusData): Selection {
  const game = data.games[0]
  const pick = data.picks.find((p) => p.board === game?.board && p.game === game.game) ?? data.picks[0]
  if (pick) return { board: pick.board, game: pick.game, a: pick.a, b: pick.b }
  return { board: game?.board ?? 'macro', game: game?.game ?? 'tetris', a: data.models[0] ?? '', b: data.models[1] ?? '' }
}

/** One pick per game first, then the second of each, and so on. */
function interleave(data: VersusData, count: number): VersusData['picks'] {
  const byGame = data.games.map((g) => data.picks.filter((p) => p.board === g.board && p.game === g.game))
  const out: VersusData['picks'] = []
  for (let round = 0; out.length < count && byGame.some((list) => list.length > round); round++) {
    for (const list of byGame) {
      const pick = list[round]
      if (pick && out.length < count) out.push(pick)
    }
  }
  return out
}

function navigate(selection: Selection) {
  window.location.hash = href.versusPick(selection.board, selection.game, selection.a, selection.b)
}

function interest(row: SeedRow): number[] {
  return [row.floored ? 1 : 0, -(row.leadChanges ?? 0), row.chase ? 0 : 1, Math.abs(row.margin ?? 99), row.seed]
}

function byInterest(x: SeedRow, y: SeedRow): number {
  const a = interest(x)
  const b = interest(y)
  for (let i = 0; i < a.length; i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0)
    if (d !== 0) return d
  }
  return 0
}

function ModelSelect({ label, side, value, models, index, onChange }: { label: string; side: 'a' | 'b'; value: string; models: string[]; index: ArenaIndex; onChange: (id: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      <span className="inline-flex items-center gap-1.5">
        <TeamDot side={side} className="size-2.5" />
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => {
          onChange(event.target.value)
        }}
        className="h-11 min-w-56 rounded-lg border border-line bg-surface-2 px-3 text-sm text-fg"
      >
        {models.map((id) => (
          <option key={id} value={id}>
            {playerInfo(index, id).title}
          </option>
        ))}
      </select>
    </label>
  )
}

function SeedTable({ data, index, selection }: { data: VersusData; index: ArenaIndex; selection: Selection }) {
  const { board, game, a, b } = selection
  const names = { a: playerInfo(index, a).title, b: playerInfo(index, b).title }
  const rows = seedRows(data, board, game, a, b).filter((r) => r.a && r.b)
  const record = seriesRecord(rows)
  const total = rows.length || 1
  const sorted = [...rows].sort(byInterest)
  const spec = data.games.find((g) => g.board === board && g.game === game)
  const gameTitle = index.games[game]?.title ?? game
  const boardTitle = index.boards.find((x) => x.id === board)?.title ?? board
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl bg-surface-2 px-4 py-3">
        <div className="flex flex-col">
          <span className="text-xs text-muted">
            Series on {gameTitle}, {boardTitle.toLowerCase()} board, {rows.length} seeds
          </span>
          <div className="flex items-baseline gap-3 font-mono text-2xl font-bold tabular-nums">
            <span className={TEAM.a.text}>{record.wins}</span>
            <span className="text-sm font-normal text-muted">{record.draws} drawn</span>
            <span className={TEAM.b.text}>{record.losses}</span>
          </div>
        </div>
        <div aria-hidden="true" className="flex h-2.5 min-w-60 flex-1 overflow-hidden rounded-full bg-surface">
          <span className={TEAM.a.fill} style={{ width: `${(record.wins / total) * 100}%` }} />
          <span className="bg-faint" style={{ width: `${(record.draws / total) * 100}%` }} />
          <span className={TEAM.b.fill} style={{ width: `${(record.losses / total) * 100}%` }} />
        </div>
        <span className="max-w-72 text-xs text-muted">A seed goes to the higher score, an equal score is a draw.</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] text-sm">
          <caption className="pb-2 text-left text-xs text-muted">
            Most lead changes first, then chases, then the closest finishes; seeds where both runs end on the floor come last.
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th scope="col" className="py-2 pr-3 font-semibold">Seed</th>
              <th scope="col" className="py-2 pr-3 font-semibold">{names.a}</th>
              <th scope="col" className="py-2 pr-3 font-semibold">{names.b}</th>
              <th scope="col" className="py-2 pr-3 font-semibold">Lead changes</th>
              <th scope="col" className="py-2 pr-3 font-semibold">Why watch</th>
              <th scope="col" className="py-2 text-right font-semibold">Replay</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const sa = row.a?.[0] ?? 0
              const sb = row.b?.[0] ?? 0
              return (
                <tr key={row.seed} className="border-b border-line/60">
                  <td className="py-1 pr-3 font-mono text-muted">{row.seed}</td>
                  <td className="py-1 pr-3">
                    <span className={`font-mono ${sa > sb ? `font-bold ${TEAM.a.text}` : ''}`}>{formatScore(game, sa)}</span>{' '}
                    <span className="text-xs text-muted">
                      {row.a?.[1] ?? '—'} {spec?.unit ?? ''}s, {row.a?.[2]}
                    </span>
                  </td>
                  <td className="py-1 pr-3">
                    <span className={`font-mono ${sb > sa ? `font-bold ${TEAM.b.text}` : ''}`}>{formatScore(game, sb)}</span>{' '}
                    <span className="text-xs text-muted">
                      {row.b?.[1] ?? '—'} {spec?.unit ?? ''}s, {row.b?.[2]}
                    </span>
                  </td>
                  <td className="py-1 pr-3 font-mono">{row.leadChanges ?? '—'}</td>
                  <td className="py-1 pr-3 text-xs text-muted">{whyWatch(row, names)}</td>
                  <td className="py-1 text-right">
                    <a href={href.match(board, game, a, b, row.seed)} className="inline-flex min-h-10 items-center font-semibold">
                      Watch
                    </a>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function DuelSectionView({ data, index, a, b }: { data: VersusData; index: ArenaIndex; a: string; b: string }) {
  const duel = data.duel
  if (!duel) {
    return <p className="text-sm text-muted">No direct games have been exported yet (arena duel run, then arena export).</p>
  }
  const ranked = Object.entries(duel.ratings).sort(([, x], [, y]) => y.elo - x.elo)
  const pair = pairId(a, b)
  const games = duel.games[pair] ?? []
  const [first] = splitPair(pair)
  const names = { a: playerInfo(index, a).title, b: playerInfo(index, b).title }
  const seeds = [...new Set(games.map((g) => g.seed))].sort((x, y) => x - y)
  const points = duel.pairs[pair]?.points ?? {}
  const label = (result: string, x: string) => (result === 'draw' ? 'draw' : result === 'X' ? `${playerInfo(index, x).title} wins` : `${playerInfo(index, x === a ? b : a).title} wins`)
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Ratings from {Object.values(duel.games).reduce((t, g) => t + g.length, 0)} direct games</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th scope="col" className="py-1.5 pr-2 font-semibold">#</th>
                <th scope="col" className="py-1.5 pr-2 font-semibold">Model</th>
                <th scope="col" className="py-1.5 pr-2 text-right font-semibold">Elo</th>
                <th scope="col" className="py-1.5 pr-2 font-semibold">95% interval</th>
                <th scope="col" className="py-1.5 text-right font-semibold">Points</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map(([id, rating], i) => (
                <tr key={id} className={`border-b border-line/60 ${id === a || id === b ? 'bg-surface-2' : ''}`}>
                  <td className="py-1 pr-2 font-mono text-muted">{i + 1}</td>
                  <td className="py-1 pr-2">
                    {id === a ? <TeamDot side="a" className="mr-1.5 size-2" /> : id === b ? <TeamDot side="b" className="mr-1.5 size-2" /> : null}
                    {playerInfo(index, id).title}
                  </td>
                  <td className="py-1 pr-2 text-right font-mono font-bold">{formatNumber(rating.elo, 0)}</td>
                  <td className="py-1 pr-2 font-mono text-xs text-muted">{rating.interval ? `${formatNumber(rating.interval[0], 0)} to ${formatNumber(rating.interval[1], 0)}` : '—'}</td>
                  <td className="py-1 text-right font-mono">
                    {formatNumber(rating.points, 1)} / {rating.games}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-muted">Bradley–Terry on the Elo scale, the mean model at 1500; intervals resample the openings.</p>
        </div>
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">
            {names.a} vs {names.b}:{' '}
            <span className={`font-mono ${TEAM.a.text}`}>{formatNumber(points[a] ?? 0, 1)}</span> :{' '}
            <span className={`font-mono ${TEAM.b.text}`}>{formatNumber(points[b] ?? 0, 1)}</span>
          </h3>
          {games.length === 0 ? (
            <p className="text-sm text-muted">This pair has not played yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[30rem] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th scope="col" className="py-1.5 pr-2 font-semibold">Opening</th>
                    <th scope="col" className="py-1.5 pr-2 font-semibold">Game 1 ({playerInfo(index, first).title} is X)</th>
                    <th scope="col" className="py-1.5 font-semibold">Game 2 (colours swapped)</th>
                  </tr>
                </thead>
                <tbody>
                  {seeds.map((seed) => {
                    const opening = duel.openings[String(seed)]
                    return (
                      <tr key={seed} className="border-b border-line/60">
                        <td className="py-1 pr-2 font-mono text-xs text-muted">
                          {seed} · X c{opening?.[0]}, O c{opening?.[1]}
                        </td>
                        {[1, 2].map((gameNo) => {
                          const g = games.find((x) => x.seed === seed && x.game_no === gameNo)
                          return (
                            <td key={gameNo} className="py-1 pr-2">
                              {g ? (
                                <a href={href.duel(a, b, seed, gameNo)} className="inline-flex min-h-9 items-center">
                                  {label(g.result, g.x)} · {g.moves} moves
                                </a>
                              ) : (
                                <span className="text-muted">not played</span>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function VersusView({ index, selection: wanted }: { index: ArenaIndex; selection: Partial<Selection> }) {
  const data = use(versusResource())
  const base = defaults(data)
  const selection: Selection = {
    board: wanted.board ?? base.board,
    game: wanted.game ?? base.game,
    a: wanted.a && data.models.includes(wanted.a) ? wanted.a : base.a,
    b: wanted.b && data.models.includes(wanted.b) ? wanted.b : base.b,
  }
  const direct = selection.board === DIRECT
  const models = data.models
  const set = (patch: Partial<Selection>) => {
    navigate({ ...selection, ...patch })
  }
  const chips = [
    ...data.games.map((g) => ({ board: g.board, game: g.game, label: `${index.games[g.game]?.title ?? g.game} · ${index.boards.find((b) => b.id === g.board)?.title.toLowerCase() ?? g.board}` })),
    ...(data.duel ? [{ board: DIRECT, game: 'connect4', label: 'Connect Four · direct' }] : []),
  ]
  const picks = interleave(data, 9)
  return (
    <div className="flex flex-col gap-6">
      <div className="flex max-w-3xl flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Versus</h1>
        <p className="text-muted">
          Two models, one seed: the same pieces, the same food, the same emulator start, the same option order. Pick a pair and a game, or start
          from a match worth watching. In Connect Four the models play each other directly.
        </p>
      </div>

      <Card className="flex flex-col gap-4 p-5">
        <h2 className="text-base font-semibold">Pick a match</h2>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
          <ModelSelect label="Left" side="a" value={selection.a} models={models.filter((m) => m !== selection.b)} index={index} onChange={(a) => { set({ a }) }} />
          <span aria-hidden="true" className="pb-3 font-bold text-faint">
            vs
          </span>
          <ModelSelect label="Right" side="b" value={selection.b} models={models.filter((m) => m !== selection.a)} index={index} onChange={(b) => { set({ b }) }} />
          <button
            type="button"
            onClick={() => {
              set({ a: selection.b, b: selection.a })
            }}
            className="h-11 rounded-lg border border-line px-3 text-sm text-muted hover:text-fg"
          >
            Swap sides
          </button>
        </div>
        <div role="group" aria-label="Game" className="flex flex-wrap gap-1.5">
          {chips.map((chip) => {
            const active = chip.board === selection.board && chip.game === selection.game
            return (
              <button
                key={`${chip.board}/${chip.game}`}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  set({ board: chip.board, game: chip.game })
                }}
                className={`h-10 rounded-full border px-3.5 text-sm ${active ? 'border-accent bg-accent-soft font-semibold text-accent-strong' : chip.board === DIRECT ? 'border-dashed border-faint text-muted' : 'border-line text-muted'}`}
              >
                {chip.label}
              </button>
            )
          })}
        </div>
        {data.excluded.some((e) => e.game === 'tetris') ? (
          <p className="text-xs text-muted">Tetris on the frame and real-time boards is left out: every model clears 0 lines there, so only survival would differ.</p>
        ) : null}
        {direct ? <DuelSectionView data={data} index={index} a={selection.a} b={selection.b} /> : <SeedTable data={data} index={index} selection={selection} />}
      </Card>

      <section aria-labelledby="picks" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="picks" className="text-lg font-semibold">
            Worth watching
          </h2>
          <span className="text-xs text-muted">The best match of each game: most lead changes, then a chase, then the closest finish</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {picks.map((pick) => {
            const key = `${pick.board}/${pick.game}`
            const sa = data.episodes[key]?.[pick.a]?.[String(pick.seed)]?.[0] ?? 0
            const sb = data.episodes[key]?.[pick.b]?.[String(pick.seed)]?.[0] ?? 0
            return (
              <a
                key={`${key}/${pick.a}/${pick.b}/${pick.seed}`}
                href={href.match(pick.board, pick.game, pick.a, pick.b, pick.seed)}
                className="flex flex-col gap-2.5 rounded-xl border border-line bg-surface p-4 text-fg no-underline hover:border-accent hover:text-fg"
              >
                <span className="text-xs font-semibold tracking-wide text-muted uppercase">
                  {index.games[pick.game]?.title ?? pick.game} · {pick.board} · seed {pick.seed}
                </span>
                <span className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
                  <span className="truncate font-semibold">{playerInfo(index, pick.a).title}</span>
                  <span className="font-mono text-lg font-bold tabular-nums">
                    {formatScore(pick.game, sa)} – {formatScore(pick.game, sb)}
                  </span>
                  <span className="truncate text-right font-semibold">{playerInfo(index, pick.b).title}</span>
                </span>
                <span className="flex flex-wrap gap-1.5 text-xs text-muted">
                  <span className="rounded-full bg-surface-2 px-2 py-0.5">{pick.lead_changes} lead changes</span>
                  {pick.chase ? <span className="rounded-full bg-surface-2 px-2 py-0.5">a chase</span> : null}
                  <span className="rounded-full bg-surface-2 px-2 py-0.5">margin {formatScore('tetris', pick.margin)}</span>
                </span>
              </a>
            )
          })}
        </div>
      </section>
    </div>
  )
}
