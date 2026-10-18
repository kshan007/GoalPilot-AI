import { expect, request as playwrightRequest, test, type Page } from '@playwright/test'

/**
 * Browser acceptance for the surfaces added in the completion pass.
 *
 * Seeding goes through the API (fast, deterministic); the browser is used for what only a
 * browser can prove: routing, render, form submission, and that a slow model call resolves into
 * a visible recommendation rather than a stuck spinner.
 */
const API = process.env.API_URL ?? 'http://127.0.0.1:8000/api'
const EMAIL = `pw.e2e.${Date.now()}@example.com`
const PASSWORD = 'Str0ng-Passw0rd!'

const PROFILE = {
  monthly_income: 120000,
  essential_expenses: 45000,
  discretionary_expenses: 10000,
  monthly_savings_target: 15000,
  preferred_cash_buffer: 8000,
  emergency_months: 6,
  emi_income_ratio_cap: 0.35,
  risk_capacity: 0.55,
  inflation_assumption: 0.03,
  investment_return_assumption: 0.05,
  savings_return_assumption: 0,
  loan_interest_assumption: 0.11,
}

function iso(daysAhead: number): string {
  const d = new Date()
  d.setDate(d.getDate() + daysAhead)
  return d.toISOString().slice(0, 10)
}

async function signIn(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

test.beforeAll(async () => {
  const ctx = await playwrightRequest.newContext()
  const reg = await ctx.post(`${API}/auth/register`, {
    data: { email: EMAIL, password: PASSWORD, full_name: 'Playwright User' },
  })
  expect(reg.ok(), `register failed: ${reg.status()} ${await reg.text()}`).toBeTruthy()
  const token = (await reg.json()).access_token as string
  const headers = { Authorization: `Bearer ${token}` }

  const profile = await ctx.put(`${API}/profile`, { headers, data: PROFILE })
  expect(profile.ok(), `profile failed: ${await profile.text()}`).toBeTruthy()

  await ctx.post(`${API}/income-sources`, {
    headers,
    data: { source_type: 'salary', label: 'Salary', amount: 120000, frequency: 'monthly' },
  })
  await ctx.post(`${API}/assets`, {
    headers,
    data: {
      asset_type: 'liquid_savings',
      label: 'Savings',
      current_value: 300000,
      is_liquid: true,
      usable_for_goals: true,
    },
  })
  await ctx.post(`${API}/liabilities`, {
    headers,
    data: {
      liability_type: 'personal_loan',
      label: 'Existing PL',
      outstanding_principal: 200000,
      annual_interest_rate: 0.12,
      emi_amount: 6000,
      remaining_tenure_months: 40,
    },
  })
  for (const [name, cost, days, priority] of [
    ['Child education', 1200000, 2200, 5],
    ['Car down payment', 400000, 900, 3],
  ] as const) {
    const goal = await ctx.post(`${API}/goals`, {
      headers,
      data: {
        name,
        purpose: '',
        goal_type: 'custom',
        current_cost: cost,
        target_date: iso(days),
        current_funded_amount: 25000,
        priority,
        criticality: 3,
        date_flexible: true,
        amount_flexible: true,
      },
    })
    expect(goal.ok(), `goal ${name} failed: ${await goal.text()}`).toBeTruthy()
  }
  await ctx.dispose()
})

test('signs in and leaves the login screen', async ({ page }) => {
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeHidden()
})

test('investment discovery renders sourced options and its provenance', async ({ page }) => {
  await signIn(page)
  await page.goto('/investments')
  await expect(page.getByRole('heading', { name: 'Explore investments' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Sources and freshness' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What is missing' })).toBeVisible()
  // Either live AMFI rows or clearly-labelled category scenarios must be present.
  await expect(page.locator('body')).toContainText(/AMFI|category scenario|scenario/i)
})

test('loan comparison shows a benchmark, published rates and labelled scenarios', async ({ page }) => {
  await signIn(page)
  await page.goto('/loans')
  await expect(page.getByRole('heading', { name: 'Loans and financing' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Historical benchmark' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Analyse an offer you have' })).toBeVisible()
  await expect(page.locator('body')).toContainText(/published|advertised/i)
})

test('generating a recommendation resolves into visible text', async ({ page }) => {
  test.setTimeout(180_000)
  await signIn(page)
  await page.goto('/recommendations')
  await expect(page.getByRole('heading', { name: 'Your plan, explained' })).toBeVisible()
  await page.getByRole('button', { name: /Generate recommendation|Regenerate/ }).click()
  // The button only returns to "Regenerate" once a response has been stored and rendered.
  await expect(page.getByRole('button', { name: 'Regenerate' })).toBeVisible({ timeout: 150_000 })
  const body = await page.locator('body').innerText()
  expect(body.length).toBeGreaterThan(400)
  expect(body).toMatch(/buffer|Buffer/)
})

test('the plan persists across a page reload', async ({ page }) => {
  await signIn(page)
  await page.goto('/goals')
  // Wait for the list to render: sampling body text straight after navigation captures the
  // "Loading your goals..." placeholder and fails for a reason that has nothing to do with
  // persistence.
  await expect(page.getByText('Child education')).toBeVisible()
  const before = await page.locator('body').innerText()
  await page.reload()
  await expect(page.getByText('Child education')).toBeVisible()
  const after = await page.locator('body').innerText()
  expect(after.length).toBeGreaterThan(0)
  expect(after).toContain('Child education')
  expect(before).toContain('Child education')
})
