import { Chip } from '../components/ui'
import { formatCompact, formatMs, formatValue, metricLabel } from '../lib/format'
import type { Replay, ReplayCall, ReplayDecision } from '../lib/types'

function CallCard({ call, texts }: { call: ReplayCall; texts: Map<string, string> }) {
  const probabilities = call.p
  return (
    <div className="rounded-lg border border-line p-2.5">
      <div className="mb-1.5 flex items-center justify-between gap-2 text-xs text-muted">
        <span className="font-medium text-fg">{call.stage}</span>
        <span className="font-mono tabular-nums">{formatMs(call.ms)}</span>
      </div>
      <ol className="flex flex-col gap-1" aria-label={`Options shown in ${call.stage}, in order`}>
        {call.keys.map((key, position) => {
          const p = probabilities?.[key]
          const chosen = key === call.choice
          return (
            <li key={key} className="grid grid-cols-[1.25rem_1fr_3.25rem] items-center gap-2 text-xs">
              <span className="text-right font-mono text-faint">{position + 1}</span>
              <div className="relative min-w-0 overflow-hidden rounded-sm bg-surface-2">
                {p !== undefined ? (
                  <div
                    className={`absolute inset-y-0 left-0 ${chosen ? 'bg-accent/45' : 'bg-faint/30'}`}
                    style={{ width: `${Math.max(0, Math.min(1, p)) * 100}%` }}
                    role="presentation"
                  />
                ) : null}
                <span
                  className={`relative block truncate px-1.5 py-0.5 ${chosen ? 'font-semibold text-fg' : 'text-muted'}`}
                  title={texts.get(key) ?? key}
                >
                  {chosen ? '✓ ' : ''}
                  <span className="font-mono">{key}</span>
                </span>
              </div>
              <span className="text-right font-mono tabular-nums text-muted" aria-label={p !== undefined ? `probability ${p.toFixed(3)}` : 'no probability'}>
                {p !== undefined ? p.toFixed(2) : '—'}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function DecisionPanel({
  decision,
  onHoverOption,
}: {
  decision: ReplayDecision
  /** Called with an option's key while it is pointed at or focused (macro Tetris previews its landing). */
  onHoverOption?: ((key: string | null) => void) | undefined
}) {
  const texts = new Map(decision.options.map((option) => [option.key, option.text]))
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Chose</span>
          <span className="font-mono font-semibold text-fg">{decision.choice}</span>
          {decision.forced ? (
            <Chip tone="anchor" title="Only one legal option: the move is not asked">
              forced
            </Chip>
          ) : null}
        </div>
        <p className="mt-1 text-sm text-fg">{texts.get(decision.choice)}</p>
      </div>

      <section aria-labelledby="options-heading">
        <h3 id="options-heading" className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">
          Options <span className="font-normal normal-case">(engine order)</span>
        </h3>
        <ul className="flex flex-col gap-1">
          {decision.options.map((option) => {
            const chosen = option.key === decision.choice
            return (
              <li
                key={option.key}
                aria-current={chosen ? 'true' : undefined}
                tabIndex={onHoverOption ? 0 : undefined}
                onMouseEnter={onHoverOption ? () => { onHoverOption(option.key) } : undefined}
                onMouseLeave={onHoverOption ? () => { onHoverOption(null) } : undefined}
                onFocus={onHoverOption ? () => { onHoverOption(option.key) } : undefined}
                onBlur={onHoverOption ? () => { onHoverOption(null) } : undefined}
                className={`rounded-md border px-2 py-1 text-xs leading-snug ${
                  chosen ? 'border-accent bg-accent-soft text-fg' : 'border-line text-muted'
                } ${onHoverOption ? 'cursor-default hover:border-faint' : ''}`}
              >
                <span className="font-mono font-medium text-fg">{option.key}</span> {option.text}
              </li>
            )
          })}
        </ul>
      </section>

      {decision.calls.length > 0 ? (
        <section aria-labelledby="calls-heading">
          <h3 id="calls-heading" className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">
            Requests <span className="font-normal normal-case">(options in the order shown, with probabilities)</span>
          </h3>
          <div className="flex flex-col gap-2">
            {decision.calls.map((call, i) => (
              <CallCard key={`${call.stage}-${i}`} call={call} texts={texts} />
            ))}
          </div>
        </section>
      ) : (
        <p className="text-xs text-faint">
          {decision.forced ? 'Forced move: nothing was asked.' : 'A baseline: it reads the game state directly and sends no requests.'}
        </p>
      )}

      <section aria-labelledby="instructions-heading">
        <h3 id="instructions-heading" className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">
          Instructions
        </h3>
        <p className="text-xs leading-relaxed text-muted">{decision.instructions}</p>
      </section>

      <details>
        <summary className="text-xs font-semibold tracking-wide text-muted uppercase">State text (exactly as sent)</summary>
        <pre className="mt-2 max-h-96 overflow-auto rounded-lg border border-line bg-surface-2 p-3 font-mono text-[11px] leading-snug whitespace-pre-wrap text-fg">
          {decision.state}
        </pre>
      </details>
    </div>
  )
}

/** The last frame of a replay: the position after the last move. Nothing is asked here. */
export function FinalPanel({
  replay,
  scoreLabel,
  step,
  decisions,
}: {
  replay: Replay
  scoreLabel: string | undefined
  step: number
  decisions: number
}) {
  const metrics = Object.entries(replay.metrics)
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-base font-semibold tracking-tight text-fg">End of game</h2>
      <p className="text-sm text-muted">
        Final score <span className="font-mono text-lg font-semibold text-fg">{formatCompact(replay.score)}</span>
        {scoreLabel ? <span className="ml-1">({scoreLabel})</span> : null}
      </p>
      {metrics.length > 0 ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          {metrics.map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="text-muted">{metricLabel(name)}</dt>
              <dd className="font-mono text-fg">{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <p className="text-xs text-faint">
        The position after the last move, at game step {step}, following {decisions} decision{decisions === 1 ? '' : 's'}. Nothing
        is asked here.
      </p>
    </div>
  )
}
