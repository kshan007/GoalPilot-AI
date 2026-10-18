import { useLocation } from 'react-router-dom'

export default function Privacy() {
  const location = useLocation()

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-12 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Privacy, terms and disclaimer
      </h1>
      <p className="mt-2 text-sm text-slate-500">
        These statements describe what this prototype actually does. They are not a substitute for a
        legal privacy policy or a regulated terms of service.
      </p>

      <section id="privacy" className="mt-10 scroll-mt-24">
        <h2 className="text-lg font-semibold text-slate-900">Privacy</h2>
        <ul className="mt-3 space-y-2 text-sm text-slate-600">
          <li>
            The data you enter belongs to your account. Every API request is scoped to the
            authenticated user, and records are never surfaced to another account.
          </li>
          <li>
            A bearer token identifies the session. It is stored in the browser under the
            localStorage key <span className="font-mono text-xs">gp_token</span> and sent in the
            Authorization header on every authenticated request. It is not placed in a URL.
          </li>
          <li>
            Signing out rotates the account's token version, which revokes every existing session for
            that account. A leaked token cannot survive a sign-out.
          </li>
          <li>
            Passwords are stored only as a hash. A password reset token is single-use and expires. No
            secret is ever returned in an API response or included in a data export.
          </li>
          <li>
            The platform never asks for bank, broker or lender credentials and holds no such
            connection.
          </li>
          <li>
            A full JSON export of the records held for your account is available from the account
            page. Account deletion removes the account and its owned records.
          </li>
        </ul>
      </section>

      <section id="terms" className="mt-10 scroll-mt-24">
        <h2 className="text-lg font-semibold text-slate-900">Terms of use</h2>
        <ul className="mt-3 space-y-2 text-sm text-slate-600">
          <li>
            This is a research and academic prototype. It is provided as-is, without warranty, and
            without any commitment to availability or accuracy.
          </li>
          <li>
            You are responsible for the accuracy of anything you record. Estimates and projections
            produced by the platform are derived from the assumptions stated at the time they were
            produced, and those assumptions are shown with every result.
          </li>
          <li>
            The platform does not execute trades, transfer money, open accounts or originate loans,
            and it does not connect to any financial institution.
          </li>
          <li>
            You may export and delete your data at any time from the account page. Deleting the
            account is irreversible.
          </li>
        </ul>
      </section>

      <section id="disclaimer" className="mt-10 scroll-mt-24">
        <h2 className="text-lg font-semibold text-slate-900">Disclaimer</h2>
        <p className="mt-3 text-sm text-slate-600">
          GoalPilot AI is an academic research and decision-support prototype. It does not provide
          personalised or regulated financial advice, it does not guarantee any return, and it does
          not execute trades, move money or originate loans. Every rate, return and projection shown
          is an assumption or a synthetic value, clearly labelled as such.
        </p>
        <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          Research decision-support prototype. Not financial advice. No trades, transfers or loans are
          executed.
        </p>
      </section>

      <section className="mt-10 scroll-mt-24">
        <h2 className="text-lg font-semibold text-slate-900">Educational disclaimer</h2>
        <p className="mt-3 text-sm text-slate-600">
          The educational layer in this platform is general explanatory text. It is not a quotation
          from, and carries no citation to, any external institution or publication. Course-stated
          rates, tax rules and eligibility conditions are treated as potentially outdated and are not
          restated as current fact. The educational content never feeds numbers into the optimiser and
          cannot override a financial constraint.
        </p>
        <p className="mt-3 text-xs text-slate-500">
          On: {location.pathname}
          {location.hash ? ` (section ${location.hash.replace('#', '')})` : ''}
        </p>
      </section>
    </div>
  )
}
