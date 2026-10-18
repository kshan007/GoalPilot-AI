import { useState } from 'react'
import { errorMessage, optimizeApi } from '../api/client'
import type { ComparisonResponse } from '../api/types'
import { formatDateTime, formatMoney, formatPct, formatPctRaw, valueText } from '../lib/format'
import { ComparisonBars, type ComparisonBarRow } from '../components/Charts'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineNotice,
  JsonBlock,
  LoadingState,
  PageHeader,
  StatCard,
  WarningList,
} from '../components/ui'

function metricValue(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key]
  return typeof value === 'number' ? value : null
}

/** One row per metric, one column per arm. Every arm is measured the same way. */
const COMPARABLE_ROWS: Array<{ key: string; label: string; kind: 'pct' | 'money' | 'number' }> = [
  { key: 'weighted_goal_achievement', label: 'Weighted goal achievement', kind: 'pct' },
  { key: 'pct_goals_met_by_deadline', label: 'Goals met by deadline', kind: 'pct' },
  { key: 'total_shortfall', label: 'Total shortfall at deadline', kind: 'money' },
  { key: 'monthly_contribution_planned', label: 'Planned monthly contribution', kind: 'money' },
  { key: 'monthly_contribution_credited_avg', label: 'Average credited per month', kind: 'money' },
  { key: 'monthly_savings_credited_avg', label: '… through savings', kind: 'money' },
  { key: 'monthly_investment_credited_avg', label: '… through investment', kind: 'money' },
  { key: 'unallocated_budget_total', label: 'Budget left unallocated', kind: 'money' },
  { key: 'final_cash', label: 'Final cash (incl. earmarked)', kind: 'money' },
  { key: 'final_unearmarked_cash', label: 'Final cash not earmarked', kind: 'money' },
  { key: 'earmarked_goal_funding', label: 'Earmarked to goals (memo)', kind: 'money' },
  { key: 'final_portfolio', label: 'Final portfolio', kind: 'money' },
  { key: 'final_liabilities', label: 'Final liabilities', kind: 'money' },
  { key: 'net_worth', label: 'Net worth', kind: 'money' },
  { key: 'months_simulated', label: 'Months simulated', kind: 'number' },
]

function renderCell(value: unknown, kind: 'pct' | 'money' | 'number'): string {
  if (typeof value !== 'number') return 'not measured'
  if (kind === 'pct') return formatPct(value)
  if (kind === 'money') return formatMoney(value)
  return String(value)
}

/**
 * The comparison is presented as evidence, not as a ranking. An arm that did not run has no
 * metric at all, and that is stated explicitly rather than shown as a zero.
 */
export default function Compare() {
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function runComparison() {
    setPending(true)
    setError(null)
    try {
      const response = await optimizeApi.compare()
      setComparison(response)
    } catch (caught) {
      setError(errorMessage(caught))
      setComparison(null)
    } finally {
      setPending(false)
    }
  }

  const barRows: ComparisonBarRow[] = (comparison?.arms ?? [])
    .filter((arm) => arm.available)
    .map((arm) => ({
      label: arm.label,
      weighted_goal_achievement: metricValue(arm.metrics, 'weighted_goal_achievement'),
      pct_goals_met_by_deadline: metricValue(arm.metrics, 'pct_goals_met_by_deadline'),
    }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Compare algorithms"
        description="Every arm that can actually run is scored on the same cash flow and the same goals. The comparison reports what ran and what did not; it does not assume the reinforcement-learning arm is superior."
        actions={
          <Button pending={pending} onClick={runComparison}>
            Run comparison
          </Button>
        }
      />

      {error && <ErrorState message={error} onRetry={runComparison} />}

      {pending && <LoadingState label="Running every available arm..." />}

      {!pending && !comparison && !error && (
        <EmptyState
          title="No comparison has been run in this session"
          message="Run the comparison to score each available algorithm. At least one active goal is required; if there is none the API will say so."
        />
      )}

      {comparison && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Comparison run" value={`#${comparison.run_id}`} hint={comparison.selector_version} />
            <StatCard
              label="Recommended"
              value={comparison.recommended_algorithm}
              hint={comparison.sufficient_evidence_for_change ? 'Evidence supports a change' : 'Evidence does not support a change'}
            />
            <StatCard label="Capacity ratio" value={formatPctRaw(comparison.capacity_ratio * 100, 2)} />
            <StatCard label="Runtime" value={`${comparison.runtime_ms} ms`} />
          </section>

          <Card
            title="Recommendation"
            description="The selector's stated reason, and whether the evidence is sufficient to change the current choice."
          >
            <div className="space-y-3">
              <InlineNotice tone="info">{comparison.recommendation_reason}</InlineNotice>
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <tbody>
                    <tr>
                      <td className="text-slate-500">Recommended algorithm</td>
                      <td className="font-medium">{comparison.recommended_algorithm}</td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Sufficient evidence to change</td>
                      <td>
                        <Badge tone={comparison.sufficient_evidence_for_change ? 'positive' : 'neutral'}>
                          {comparison.sufficient_evidence_for_change ? 'yes' : 'no'}
                        </Badge>
                      </td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Capacity ratio</td>
                      <td className="font-mono text-sm">{formatPctRaw(comparison.capacity_ratio * 100, 2)}</td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Capacity derivation</td>
                      <td className="text-sm">{comparison.capacity_derivation}</td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Created</td>
                      <td>{formatDateTime(comparison.created_at)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </Card>

          <Card
            title="Arms that ran"
            description="A metric only exists where something actually executed. An unavailable arm is shown with no metric and with the reason."
          >
            {barRows.length > 0 && (
              <div className="mb-6">
                <ComparisonBars data={barRows} />
              </div>
            )}

            {comparison.arms.length > 0 && (
              <div className="mb-6 overflow-x-auto">
                <p className="mb-2 text-sm font-medium text-slate-700">
                  Side by side, on one definition
                </p>
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      {comparison.arms.map((arm) => (
                        <th key={arm.algorithm} className="gp-num">
                          {arm.algorithm}
                          {!arm.ranked && (
                            <span className="block text-xs font-normal text-slate-400">
                              reported, not ranked
                            </span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {COMPARABLE_ROWS.map((row) => (
                      <tr key={row.key}>
                        <td className="text-slate-600" title={comparison.metric_definitions[row.key]}>
                          {row.label}
                        </td>
                        {comparison.arms.map((arm) => (
                          <td key={arm.algorithm} className="gp-num">
                            {renderCell(arm.metrics_comparable[row.key], row.kind)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-xs text-slate-500">
                  Hover a metric for its definition. A missing value means the arm did not
                  measure it — it is never shown as zero. “Planned” is the optimiser's monthly
                  instruction; “credited” is what the simulator actually moved over the episode,
                  which is lower once a goal is fully funded and further contributions are capped.
                </p>
              </div>
            )}

            {comparison.arms.length === 0 ? (
              <EmptyState
                title="No arms were returned"
                message="The comparison returned no arm at all, so there is nothing to score."
              />
            ) : (
              <div className="space-y-4">
                {comparison.arms.map((arm) => {
                  const metrics = Object.entries(arm.metrics)
                  return (
                    <article key={arm.algorithm} className="rounded-md border border-slate-200 p-4">
                      <header className="flex flex-wrap items-center gap-3">
                        <h3 className="text-sm font-semibold text-slate-900">{arm.label}</h3>
                        <span className="font-mono text-xs text-slate-500">{arm.algorithm}</span>
                        <Badge tone={arm.available ? 'positive' : 'neutral'}>
                          {arm.available ? 'available' : 'unavailable'}
                        </Badge>
                        <Badge tone={arm.feasible ? 'positive' : 'warning'}>
                          {arm.feasible ? 'feasible' : 'not feasible'}
                        </Badge>
                        <Badge tone="neutral">status: {arm.status}</Badge>
                        <Badge tone={arm.ranked ? 'positive' : 'neutral'}>
                          {arm.ranked ? 'ranked' : 'not ranked'}
                        </Badge>
                      </header>

                      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-slate-500">Metric basis</dt>
                          <dd className="text-slate-700">{arm.metric_basis}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-slate-500">Runtime</dt>
                          <dd className="font-mono text-slate-700">{arm.runtime_ms} ms</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-slate-500">Model version</dt>
                          <dd className="font-mono text-slate-700">{arm.model_version}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-slate-500">Feasible</dt>
                          <dd className="text-slate-700">{arm.feasible ? 'yes' : 'no'}</dd>
                        </div>
                      </dl>

                      <div className="mt-3">
                        <p className="text-xs uppercase tracking-wide text-slate-500">
                          Raw metrics (engine-specific — compare only through the table above)
                        </p>
                        {metrics.length === 0 ? (
                          <p className="mt-1 text-sm text-amber-800">
                            No metric exists for this arm because nothing ran. There is no score to
                            report, and a missing score is not the same as a score of zero.
                          </p>
                        ) : (
                          <div className="mt-1 overflow-x-auto">
                            <table className="gp-table">
                              <tbody>
                                {metrics.map(([key, value]) => (
                                  <tr key={key}>
                                    <td className="text-slate-500">{key.replace(/_/g, ' ')}</td>
                                    <td className="gp-num">
                                      {typeof value === 'number' && key.startsWith('pct')
                                        ? formatPct(value)
                                        : typeof value === 'number' && key.includes('achievement')
                                          ? formatPct(value)
                                          : valueText(value)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>

                      {arm.fallback_reason && (
                        <div className="mt-3">
                          <InlineNotice tone="warning">
                            This arm did not run as configured: {arm.fallback_reason}
                          </InlineNotice>
                        </div>
                      )}

                      {arm.warnings.length > 0 && (
                        <div className="mt-3">
                          <WarningList warnings={arm.warnings} />
                        </div>
                      )}
                    </article>
                  )
                })}
              </div>
            )}
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Not selected" description="Arms that were evaluated but not recommended, with the reason for each.">
              {comparison.not_selected.length === 0 ? (
                <EmptyState
                  title="Nothing was set aside"
                  message="The selector did not exclude any arm in this comparison."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <thead>
                      <tr>
                        <th>Algorithm</th>
                        <th>Label</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.not_selected.map((item) => (
                        <tr key={item.algorithm}>
                          <td className="font-mono text-xs">{item.algorithm}</td>
                          <td>{item.label}</td>
                          <td className="text-sm text-slate-600">{item.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Decision rule" description="The thresholds the selector applied, verbatim.">
              {Object.keys(comparison.decision_rule).length === 0 ? (
                <EmptyState title="No decision rule recorded" message="The comparison returned no decision rule." />
              ) : (
                <JsonBlock value={comparison.decision_rule} label="decision rule" />
              )}
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Notes" description="Caveats recorded with this comparison.">
              {comparison.notes.length === 0 ? (
                <EmptyState title="No notes" message="The comparison recorded no notes." />
              ) : (
                <ul className="space-y-2 text-sm text-slate-700">
                  {comparison.notes.map((note) => (
                    <li key={note} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                      {note}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card
              title="Research reference"
              description="The research project's own recorded held-out results, reported as recorded. These are not recomputed here and are not a claim of superiority."
            >
              {Object.keys(comparison.research_reference).length === 0 ? (
                <EmptyState
                  title="No research reference available"
                  message="The research artefacts could not be read, so no reference numbers are reported."
                />
              ) : (
                <JsonBlock value={comparison.research_reference} label="research reference" />
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
