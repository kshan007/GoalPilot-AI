import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../api/client'
import { investmentsApi, type InvestmentDiscovery, type InvestmentOption } from '../api/market'

const inr = (value?: number | null) =>
  value === null || value === undefined
    ? 'not published'
    : new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value)

const pct = (value?: number | null, digits = 1) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`

function Freshness({ value }: { value: string }) {
  const tone =
    value === 'fresh'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : value === 'stale'
        ? 'bg-amber-50 text-amber-800 border-amber-200'
        : 'bg-slate-100 text-slate-600 border-slate-200'
  return (
    <span className={`rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>{value}</span>
  )
}

function OptionCard({ option }: { option: InvestmentOption }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            <span className="mr-2 text-slate-400">#{option.rank}</span>
            {option.name}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {option.category.replace(/_/g, ' ')}
            {option.sub_category ? ` · ${option.sub_category}` : ''}
            {option.issuer ? ` · ${option.issuer}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Freshness value={option.freshness} />
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600">
            {option.data_quality.replace(/_/g, ' ')}
          </span>
        </div>
      </header>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-slate-500">Risk</dt>
          <dd className="font-medium text-slate-900">{option.risk_level}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Liquidity</dt>
          <dd className="font-medium text-slate-900">
            {option.liquidity.replace(/_/g, ' ')}
            {option.lock_in_months ? ` · ${option.lock_in_months}m lock-in` : ''}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">{option.nav !== null ? 'NAV' : 'Rate'}</dt>
          <dd className="font-medium text-slate-900">
            {option.nav !== null
              ? inr(option.nav)
              : option.published_rate !== null
                ? pct(option.published_rate, 2)
                : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Suitability</dt>
          <dd className="font-medium text-slate-900">{(option.suitability.score * 100).toFixed(0)} / 100</dd>
        </div>
      </dl>

      {option.historical_returns.length > 0 && (
        <div className="mt-4 rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Trailing returns (past observations, not a forecast)
          </p>
          <ul className="mt-2 space-y-1 text-sm text-slate-700">
            {option.historical_returns.map((row) => (
              <li key={row.window}>
                <span className="font-medium">{row.window}</span> {pct(row.cagr, 2)} ·{' '}
                {row.period_start} → {row.period_end}
              </li>
            ))}
          </ul>
        </div>
      )}

      {option.suitability.reasons.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm text-emerald-800">
          {option.suitability.reasons.map((reason) => (
            <li key={reason}>+ {reason}</li>
          ))}
        </ul>
      )}
      {option.suitability.cautions.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-amber-800">
          {option.suitability.cautions.map((caution) => (
            <li key={caution}>! {caution}</li>
          ))}
        </ul>
      )}

      <footer className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <a
          className="text-blue-700 hover:underline"
          href={option.source_url || undefined}
          target="_blank"
          rel="noreferrer noopener"
        >
          {option.source_url ? 'Provider source' : 'No source URL'}
        </a>
        <span>Retrieved {option.retrieved_at ? option.retrieved_at.slice(0, 10) : 'unknown'}</span>
        {option.effective_date && <span>As of {option.effective_date}</span>}
      </footer>
    </article>
  )
}

export default function Investments() {
  const [data, setData] = useState<InvestmentDiscovery | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await investmentsApi.discover({ include_history: history, limit: 12 }))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [history])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Explore investments</h1>
          <p className="mt-1 text-sm text-slate-600">
            Sourced instruments and labelled category scenarios. Ranked by fit to your stated
            constraints — not by return, and not a recommendation to buy.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} />
            Include NAV history
          </label>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </header>

      {loading && (
        <p className="text-sm text-slate-600">
          Loading options… the first load fetches the live source feed and can take up to about
          20 seconds; later loads are cached.
        </p>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          {data.category_scenarios_used && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              Some rows are <strong>category scenarios</strong>, not products: no named
              instrument, no current NAV or rate. They exist so the page still explains the
              category when a source is unavailable.
            </div>
          )}

          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['Risk capacity', data.user_context.risk_capacity.toFixed(2)],
              ['Horizon', `${data.user_context.horizon_months} months`],
              ['Monthly capacity', inr(data.user_context.monthly_contribution_capacity)],
              ['Emergency fund', pct(data.user_context.emergency_fund_progress, 0)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </section>

          {data.market_context.historical.available && (
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-slate-900">Market context (historical)</h2>
              <p className="mt-1 text-sm text-slate-600">
                NIFTY 50, {data.market_context.historical.period_start} →{' '}
                {data.market_context.historical.period_end} · annualised volatility{' '}
                {pct(data.market_context.historical.annualised_volatility)} · max drawdown{' '}
                {pct(data.market_context.historical.max_drawdown)}
              </p>
              <p className="mt-2 text-xs text-slate-500">{data.market_context.historical.caveat}</p>
            </section>
          )}

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">
              {data.option_count} option{data.option_count === 1 ? '' : 's'}
            </h2>
            {data.tie_note && <p className="text-sm text-slate-600">{data.tie_note}</p>}
            {data.options.map((option) => (
              <OptionCard key={`${option.provider}-${option.product_id}`} option={option} />
            ))}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-slate-900">Sources and freshness</h2>
            <table className="mt-3 w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="pb-2">Provider</th>
                  <th className="pb-2">Status</th>
                  <th className="pb-2">Rows</th>
                  <th className="pb-2">Data quality</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.providers.map((provider) => (
                  <tr key={provider.provider}>
                    <td className="py-2 font-medium text-slate-800">{provider.provider}</td>
                    <td className="py-2">{provider.status}</td>
                    <td className="py-2">{provider.count ?? 0}</td>
                    <td className="py-2 text-slate-600">
                      {(provider.data_quality ?? '—').replace(/_/g, ' ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {data.missing_information.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-slate-50 p-5">
              <h2 className="text-sm font-semibold text-slate-900">What is missing</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {data.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-xs text-slate-500">{data.disclosure}</p>
          <p className="text-xs text-slate-500">{data.selection_rule}</p>
        </>
      )}
    </div>
  )
}
