import { Link } from 'react-router-dom'

const FEATURES = [
  {
    title: 'Monthly financial planning',
    body: 'Open the current month, record income and expenses, and separate recorded actuals from estimates. Every figure keeps its provenance: actual, estimated or projected.',
  },
  {
    title: 'Multi-goal optimisation',
    body: 'A capacity-constrained linear program allocates your surplus and usable existing assets across several goals at once, respecting emergency-fund and EMI-capacity limits.',
  },
  {
    title: 'Adaptive expense forecasting',
    body: 'Category-level estimates are produced from your own reconciled months. A personalised method is only used where a walk-forward backtest shows it beats a simple baseline.',
  },
  {
    title: 'LP vs RL vs hybrid comparison',
    body: 'The comparison scores every arm it can actually run on the same cash flow and reports which arms produced no metric, and why. No arm is presented as superior without evidence.',
  },
]

const ILLUSTRATIVE_ROWS = [
  { goal: 'Higher studies', target: '480,000.00', funded: '120,000.00', monthly: '9,500.00' },
  { goal: 'Vehicle replacement', target: '260,000.00', funded: '40,000.00', monthly: '4,100.00' },
  { goal: 'Emergency reserve', target: '180,000.00', funded: '95,000.00', monthly: '2,000.00' },
]

export default function Landing() {
  return (
    <div>
      {/* Hero */}
      <section className="border-b border-slate-200 bg-gradient-to-b from-white to-slate-50">
        <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-2 lg:py-20">
          <div>
            <p className="inline-flex items-center rounded-full bg-accent-50 px-3 py-1 text-xs font-medium text-accent-800">
              Research decision-support prototype
            </p>
            <h1 className="mt-5 text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl lg:text-5xl">
              Plan every goal against one honest cash flow.
            </h1>
            <p className="mt-5 max-w-xl text-base text-slate-600">
              GoalPilot AI is an academic research prototype for individual financial planning. It
              records what actually happened in a month, estimates what is coming, and solves a
              constrained multi-goal allocation from the surplus that genuinely exists.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                to="/register"
                className="rounded-md bg-accent-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-accent-700"
              >
                Create an account
              </Link>
              <Link
                to="/login"
                className="rounded-md border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Sign in
              </Link>
            </div>
            <p className="mt-5 max-w-xl text-xs text-slate-500">
              Not financial advice. No trades, transfers or loans are executed by this platform.
            </p>
          </div>

          <div className="gp-card p-5">
            <h2 className="text-sm font-semibold text-slate-900">What the platform does end to end</h2>
            <ol className="mt-4 space-y-3 text-sm text-slate-600">
              {[
                'Record income sources, assets and liabilities once, with their true structure.',
                'Open the month, seed recurring obligations, and record income and expenses.',
                'Generate category estimates, then enter actuals as the month unfolds.',
                'Reconcile estimates against actuals and keep the original forecast for audit.',
                'Solve a multi-goal allocation and compare the algorithms that can actually run.',
                'Stress the plan with scenarios and record what changed, in plain language.',
              ].map((step, index) => (
                <li key={step} className="flex gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent-100 text-xs font-semibold text-accent-800">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Core capabilities</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Each capability below maps to a surface in the application and to endpoints that are
          actually implemented on the backend.
        </p>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="gp-card p-5">
              <h3 className="text-base font-semibold text-slate-900">{feature.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Illustrative demo — clearly labelled */}
      <section className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
              Illustrative example of the output layout
            </h2>
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              Illustrative example - not real results
            </span>
          </div>
          <p className="mt-3 max-w-3xl text-sm text-slate-600">
            The table below exists only to show the shape of the allocation output. The numbers are
            invented for illustration and are not results produced by the platform. Nothing on this
            page is drawn from any account. Sign in to see figures computed from your own recorded
            data.
          </p>
          <div className="gp-card mt-6 overflow-x-auto p-0">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Goal (illustrative)</th>
                  <th className="gp-num">Future target</th>
                  <th className="gp-num">Funded so far</th>
                  <th className="gp-num">Monthly contribution</th>
                </tr>
              </thead>
              <tbody>
                {ILLUSTRATIVE_ROWS.map((row) => (
                  <tr key={row.goal}>
                    <td>{row.goal}</td>
                    <td className="gp-num">{row.target}</td>
                    <td className="gp-num">{row.funded}</td>
                    <td className="gp-num">{row.monthly}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Illustrative example - not real results, not advice, and not a projection of any return.
          </p>
        </div>
      </section>

      {/* Privacy and security */}
      <section className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Privacy and security</h2>
        <div className="mt-6 grid gap-5 sm:grid-cols-3">
          {[
            {
              title: 'Your data stays in your account',
              body: 'Every request is scoped to the authenticated account. Records are owned by the user who created them and are never shared with another account.',
            },
            {
              title: 'Token-based sessions',
              body: 'Sessions use a bearer token held in the browser and sent in the Authorization header. Signing out revokes every session for the account.',
            },
            {
              title: 'Export and delete on request',
              body: 'A full JSON export of your records is available at any time, and account deletion removes the account and its owned records.',
            },
          ].map((item) => (
            <article key={item.title} className="gp-card p-5">
              <h3 className="text-base font-semibold text-slate-900">{item.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{item.body}</p>
            </article>
          ))}
        </div>
        <p className="mt-6 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          The platform does not connect to any bank, broker or lender. No credential for a financial
          institution is ever requested.
        </p>
      </section>

      {/* Educational disclaimer */}
      <section className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6">
          <h2 className="text-lg font-semibold text-slate-900">Educational disclaimer</h2>
          <p className="mt-3 max-w-4xl text-sm text-slate-600">
            GoalPilot AI is an academic research and decision-support prototype. It does not provide
            personalised or regulated financial advice, it does not guarantee any return, and it does
            not execute trades, move money or originate loans. Every rate, return and projection
            shown is an assumption or a synthetic value, clearly labelled as such. Educational
            content in the platform is general and uncited; no external publication is quoted and no
            course-stated rate, tax rule or eligibility condition is restated as current fact.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/privacy"
              className="rounded-md bg-accent-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-accent-700"
            >
              Read privacy, terms and disclaimer
            </Link>
            <Link
              to="/register"
              className="rounded-md border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              Create an account
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
