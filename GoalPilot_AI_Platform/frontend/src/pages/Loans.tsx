import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import {
  loansApi,
  type LoanDiscovery,
  type LoanOption,
  type QuoteAnalysis,
} from '../api/market'

const inr = (value?: number | null) =>
  value === null || value === undefined
    ? '—'
    : `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value)}`

const pct = (value?: number | null, digits = 2) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`

function Verdict({ value }: { value: string }) {
  const tone =
    value === 'affordable'
      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
      : value === 'affordable_with_caution'
        ? 'bg-amber-50 text-amber-900 border-amber-200'
        : 'bg-red-50 text-red-800 border-red-200'
  return (
    <span className={`rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}

function RateClassTag({ value, label }: { value: string; label?: string }) {
  const tone =
    value === 'published_lender_rate'
      ? 'bg-blue-50 text-blue-800 border-blue-200'
      : value === 'historical_benchmark'
        ? 'bg-slate-100 text-slate-700 border-slate-300'
        : value === 'personalised_offer'
          ? 'bg-violet-50 text-violet-800 border-violet-200'
          : 'bg-amber-50 text-amber-900 border-amber-200'
  return (
    <span
      title={label}
      className={`rounded border px-2 py-0.5 text-xs font-medium ${tone}`}
    >
      {value.replace(/_/g, ' ')}
    </span>
  )
}

function OptionRow({ option }: { option: LoanOption }) {
  return (
    <tr className="align-top">
      <td className="py-3 pr-3">
        <p className="font-medium text-slate-900">{option.lender}</p>
        <p className="text-xs text-slate-500">{option.product_name}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <RateClassTag value={option.rate_class} label={option.rate_class_label} />
          <span className="text-xs text-slate-500">{option.rate_type}</span>
        </div>
      </td>
      <td className="py-3 pr-3 font-medium text-slate-900">
        {option.published_rate !== null ? pct(option.published_rate) : '—'}
        {option.scenario_rate ? (
          <p className="text-xs font-normal text-amber-800">scenario {pct(option.scenario_rate)}</p>
        ) : null}
      </td>
      <td className="py-3 pr-3">{inr(option.indicative?.monthly_emi)}</td>
      <td className="py-3 pr-3">{inr(option.indicative?.total_interest)}</td>
      <td className="py-3 pr-3">
        <Verdict value={option.affordability.verdict} />
      </td>
      <td className="py-3 text-xs text-slate-600">
        {option.source_url ? (
          <a
            className="text-blue-700 hover:underline"
            href={option.source_url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Source
          </a>
        ) : (
          'no source'
        )}
        <p>Retrieved {option.retrieved_at ? option.retrieved_at.slice(0, 10) : 'unknown'}</p>
      </td>
    </tr>
  )
}

export default function Loans() {
  // Inputs are drafts; the figures only change when Recalculate applies them. Fetching on every
  // keystroke meant the button appeared to do nothing and late responses could overwrite the
  // values for what had actually been typed.
  const [principalInput, setPrincipalInput] = useState('500000')
  const [tenureInput, setTenureInput] = useState('48')
  const [scenarioRate, setScenarioRate] = useState('')
  const [applied, setApplied] = useState({ principal: 500000, tenure: 48, scenarioRate: '', nonce: 0 })
  const [inputError, setInputError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const requestSeq = useRef(0)

  const [data, setData] = useState<LoanDiscovery | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [quote, setQuote] = useState({ rate: '10.5', feePct: '1', feeFlat: '0' })
  const [analysis, setAnalysis] = useState<QuoteAnalysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  const load = useCallback(async () => {
    // Only the newest request may write results, so a slow earlier response cannot overwrite a
    // newer calculation.
    const seq = requestSeq.current + 1
    requestSeq.current = seq
    setLoading(true)
    setError(null)
    try {
      const parsed =
        applied.scenarioRate.trim() === '' ? undefined : Number(applied.scenarioRate) / 100
      const result = await loansApi.discover({
        principal: applied.principal,
        tenure_months: applied.tenure,
        scenario_rate: Number.isFinite(parsed) ? parsed : undefined,
      })
      if (seq !== requestSeq.current) return
      setData(result)
      setUpdatedAt(new Date())
    } catch (err) {
      if (seq !== requestSeq.current) return
      setError(errorMessage(err))
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [applied])

  useEffect(() => {
    void load()
  }, [load])

  function recalculate() {
    const principal = Number(principalInput)
    const tenure = Number(tenureInput)
    if (!Number.isFinite(principal) || principal < 10000) {
      setInputError('Enter a loan amount of at least ₹10,000.')
      return
    }
    if (!Number.isFinite(tenure) || tenure < 6 || tenure > 360) {
      setInputError('Enter a term between 6 and 360 months.')
      return
    }
    setInputError(null)
    setApplied({ principal, tenure, scenarioRate, nonce: Date.now() })
  }

  async function runAnalysis() {
    setAnalysing(true)
    setAnalysisError(null)
    try {
      setAnalysis(
        await loansApi.analyse({
          principal: applied.principal,
          annual_rate: Number(quote.rate) / 100,
          tenure_months: applied.tenure,
          processing_fee_pct: quote.feePct === '' ? null : Number(quote.feePct) / 100,
          processing_fee_flat: Number(quote.feeFlat || 0),
          rate_type: 'floating',
          include_schedule: false,
        }),
      )
    } catch (err) {
      setAnalysisError(errorMessage(err))
    } finally {
      setAnalysing(false)
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Loans and financing</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Published lender rates, a historical system benchmark, and clearly labelled scenarios.
          Nothing here is an offer, an approval or a personalised rate, and the platform never
          originates a loan.
        </p>
      </header>

      <section className="grid gap-4 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-4">
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">Principal (₹)</span>
          <input
            type="number"
            min={10000}
            step={10000}
            value={principalInput}
            onChange={(e) => setPrincipalInput(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">Tenure (months)</span>
          <input
            type="number"
            min={6}
            max={360}
            value={tenureInput}
            onChange={(e) => setTenureInput(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">Scenario rate % (optional)</span>
          <input
            type="number"
            min={0}
            max={50}
            step={0.1}
            placeholder="uses profile assumption"
            value={scenarioRate}
            onChange={(e) => setScenarioRate(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={recalculate}
            disabled={loading}
            className="w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {loading ? 'Recalculating…' : 'Recalculate'}
          </button>
        </div>
      </section>

      {inputError && (
        <p className="text-sm font-medium text-red-700" role="alert">
          {inputError}
        </p>
      )}

      {updatedAt && !loading && !error && (
        <p className="text-xs text-slate-500">
          Figures calculated for {inr(data?.assumed_principal ?? applied.principal)} over{' '}
          {data?.assumed_tenure_months ?? applied.tenure} months at{' '}
          {updatedAt.toLocaleTimeString()}.
        </p>
      )}

      {loading && <p className="text-sm text-slate-600">Calculating loan options…</p>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-slate-900">
                Published lender products ({data.option_count})
              </h2>
              <p className="text-xs text-slate-500">
                EMI computed on {inr(data.assumed_principal)} over {data.assumed_tenure_months}{' '}
                months
              </p>
            </div>
            {data.options.length === 0 ? (
              <p className="mt-3 text-sm text-slate-600">
                No lender product could be read from the integrated sources. No substitute
                product has been invented.
              </p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="pb-2">Lender</th>
                      <th className="pb-2">Published rate</th>
                      <th className="pb-2">Indicative EMI</th>
                      <th className="pb-2">Total interest</th>
                      <th className="pb-2">Affordability</th>
                      <th className="pb-2">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.options.map((option) => (
                      <OptionRow key={option.product_id} option={option} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-500">
              Advertised minimum rates from each lender's public page. The rate you are offered
              depends on the lender's assessment.
            </p>
          </section>

          {data.scenarios.length > 0 && (
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <h2 className="text-lg font-semibold text-amber-900">
                Categories with no published product ({data.scenario_count})
              </h2>
              <p className="mt-1 text-sm text-amber-900">
                {data.category_coverage.note}
              </p>
              <table className="mt-3 w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-amber-800">
                  <tr>
                    <th className="pb-2">Category</th>
                    <th className="pb-2">Scenario rate</th>
                    <th className="pb-2">Assumption from</th>
                    <th className="pb-2">Indicative EMI</th>
                    <th className="pb-2">Affordability</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-amber-200">
                  {data.scenarios.map((scenario) => (
                    <tr key={scenario.product_id}>
                      <td className="py-2 font-medium text-amber-900">{scenario.category}</td>
                      <td className="py-2">{pct(scenario.scenario_rate)}</td>
                      <td className="py-2 text-xs">{(scenario.assumption_source ?? '').replace(/_/g, ' ')}</td>
                      <td className="py-2">{inr(scenario.indicative?.monthly_emi)}</td>
                      <td className="py-2">
                        <Verdict value={scenario.affordability.verdict} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-amber-800">
                These rows have <code>published_rate = null</code> by design: they are modelling
                assumptions you can change above, not market rates.
              </p>
            </section>
          )}

          {data.benchmarks.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-slate-900">Historical benchmark</h2>
              {data.benchmarks.map((benchmark) => (
                <div key={benchmark.benchmark} className="mt-2 text-sm text-slate-700">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{pct(benchmark.rate)}</span>
                    <RateClassTag value={benchmark.rate_class} />
                    <span className="text-xs text-slate-500">as of {benchmark.period}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{benchmark.benchmark}</p>
                </div>
              ))}
              <p className="mt-2 text-xs text-slate-500">
                A system-wide average is not the rate available to any individual borrower.
              </p>
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold text-slate-900">Analyse an offer you have</h2>
            <p className="mt-1 text-sm text-slate-600">
              Enter a rate you were quoted to see the true cost of credit (fees included), the
              affordability checks, and the effect of a rate rise.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <label className="text-sm text-slate-700">
                <span className="mb-1 block font-medium">Rate % p.a.</span>
                <input
                  type="number"
                  step={0.05}
                  value={quote.rate}
                  onChange={(e) => setQuote({ ...quote, rate: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="text-sm text-slate-700">
                <span className="mb-1 block font-medium">Processing fee %</span>
                <input
                  type="number"
                  step={0.1}
                  value={quote.feePct}
                  onChange={(e) => setQuote({ ...quote, feePct: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="text-sm text-slate-700">
                <span className="mb-1 block font-medium">Flat fees (₹)</span>
                <input
                  type="number"
                  step={500}
                  value={quote.feeFlat}
                  onChange={(e) => setQuote({ ...quote, feeFlat: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <div className="flex items-end">
                <button
                  type="button"
                  onClick={() => void runAnalysis()}
                  disabled={analysing}
                  className="w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  {analysing ? 'Analysing…' : 'Analyse'}
                </button>
              </div>
            </div>
            {analysisError && (
              <p className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                {analysisError}
              </p>
            )}

            {analysis && (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <RateClassTag value={analysis.rate_class} label={analysis.rate_class_label} />
                  <Verdict value={analysis.affordability.verdict} />
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  {[
                    ['Monthly EMI', inr(analysis.repayment.monthly_emi)],
                    ['Total interest', inr(analysis.repayment.total_interest)],
                    ['Fees', inr(analysis.repayment.total_fees)],
                    ['APR incl. fees', pct(analysis.repayment.apr_including_fees)],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-slate-500">{label}</dt>
                      <dd className="font-semibold text-slate-900">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-xs text-slate-500">{analysis.repayment.apr_note}</p>

                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    Floating-rate sensitivity
                  </h3>
                  <table className="mt-2 w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="pb-1">Rate</th>
                        <th className="pb-1">Shock</th>
                        <th className="pb-1">EMI</th>
                        <th className="pb-1">Increase</th>
                        <th className="pb-1">Total interest</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {analysis.rate_sensitivity.rows.map((row) => (
                        <tr key={row.rate_bump_bp}>
                          <td className="py-1">{pct(row.rate)}</td>
                          <td className="py-1">+{row.rate_bump_bp} bp</td>
                          <td className="py-1">{inr(row.emi)}</td>
                          <td className="py-1">{inr(row.emi_increase)}</td>
                          <td className="py-1">{inr(row.total_interest)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-1 text-xs text-slate-500">{analysis.rate_sensitivity.note}</p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    Alternatives to borrowing
                  </h3>
                  <ul className="mt-2 space-y-2 text-sm text-slate-700">
                    {analysis.alternatives.map((alternative) => (
                      <li key={alternative.option}>
                        <span className="font-medium">{alternative.option.replace(/_/g, ' ')}</span>{' '}
                        — {alternative.description}
                      </li>
                    ))}
                  </ul>
                </div>

                <ul className="space-y-1 text-xs text-slate-600">
                  {Object.entries(analysis.affordability.checks).map(([key, ok]) => (
                    <li key={key} className={ok ? 'text-emerald-700' : 'text-red-700'}>
                      {ok ? '✓' : '✕'} {key.replace(/_/g, ' ')}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-slate-500">{analysis.disclosure}</p>
              </div>
            )}
          </section>

          {data.missing_information.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-slate-50 p-5">
              <h2 className="text-sm font-semibold text-slate-900">Limitations of these figures</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {data.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-xs text-slate-500">{data.disclosure}</p>
        </>
      )}
    </div>
  )
}


