import { expect, request as playwrightRequest, test, type Page } from '@playwright/test'

/**
 * Release-pass browser coverage for the two workflows the original suite did not touch:
 * generating a plan (including the readiness card and the education layer) and running a
 * what-if scenario. The rest of the journey — sign-in, goals, investments, loans,
 * recommendations — is covered by `journey.spec.ts`.
 *
 * Seeding is API-level so the browser is only used for what only a browser can prove:
 * routing, rendering, interaction, and that the result arrives on screen.
 */
const API = process.env.API_URL ?? 'http://127.0.0.1:8000/api'
const EMAIL = `pw.release.${Date.now()}@example.com`
const PASSWORD = 'Str0ng-Passw0rd!'

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
    data: { email: EMAIL, password: PASSWORD, full_name: 'Release Pass User' },
  })
  expect(reg.ok(), `register failed: ${reg.status()} ${await reg.text()}`).toBeTruthy()
  const token = (await reg.json()).access_token as string
  const headers = { Authorization: `Bearer ${token}` }

  const profile = await ctx.put(`${API}/profile`, {
    headers,
    data: {
      monthly_income: 100000,
      essential_expenses: 42000,
      discretionary_expenses: 6000,
      monthly_savings_target: 15000,
      preferred_cash_buffer: 8000,
      emergency_months: 6,
      emi_income_ratio_cap: 0.35,
      risk_capacity: 0.55,
      inflation_assumption: 0.03,
      investment_return_assumption: 0.05,
      savings_return_assumption: 0,
      loan_interest_assumption: 0.12,
    },
  })
  expect(profile.ok(), `profile failed: ${await profile.text()}`).toBeTruthy()

  await ctx.post(`${API}/income-sources`, {
    headers,
    data: { source_type: 'salary', label: 'Salary', amount: 100000, frequency: 'monthly' },
  })
  await ctx.post(`${API}/assets`, {
    headers,
    data: {
      asset_type: 'liquid_savings',
      label: 'Savings',
      current_value: 200000,
      is_liquid: true,
      usable_for_goals: true,
    },
  })
  await ctx.post(`${API}/liabilities`, {
    headers,
    data: {
      liability_type: 'personal_loan',
      label: 'Existing PL',
      outstanding_principal: 600000,
      annual_interest_rate: 0.12,
      emi_amount: 12000,
      remaining_tenure_months: 60,
    },
  })
  for (const [name, cost, days, priority] of [
    ['Europe trip', 200000, 540, 3],
    ['Home down payment', 2000000, 2520, 5],
  ] as const) {
    const goal = await ctx.post(`${API}/goals`, {
      headers,
      data: {
        name,
        purpose: '',
        goal_type: 'custom',
        current_cost: cost,
        target_date: iso(days),
        current_funded_amount: 0,
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

test('builds a plan and shows allocations, readiness and the education layer', async ({ page }) => {
  test.setTimeout(180_000)
  await signIn(page)
  await page.goto('/optimize')
  await expect(page.getByRole('heading', { name: 'Your plan' })).toBeVisible()

  await page.getByRole('button', { name: 'Build my plan' }).first().click()

  // The result, not just the spinner.
  await expect(page.getByRole('heading', { name: 'Goal by goal' })).toBeVisible({ timeout: 150_000 })
  await expect(page.getByRole('heading', { name: 'Your financial safety net' })).toBeVisible()
  await expect(page.getByText('Emergency fund', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What this means' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Learn the ideas behind this plan' })).toBeVisible()

  // Readiness is reported even when it is bad, and it is not the same statement as funding.
  const body = await page.locator('body').innerText()
  expect(body).toMatch(/Emergency fund/)
  expect(body).toMatch(/of income|Protected buffer|Monthly money for goals/)
})

test('runs a what-if scenario and renders baseline, stressed and deltas', async ({ page }) => {
  test.setTimeout(150_000)
  await signIn(page)
  await page.goto('/scenarios')
  await expect(page.getByRole('heading', { name: 'Run a scenario' })).toBeVisible()

  await page.getByRole('button', { name: 'Run scenario' }).click()
  await expect(page.getByText(/Result of/)).toBeVisible({ timeout: 120_000 })
  await expect(page.getByText('Baseline', { exact: true })).toBeVisible()
  await expect(page.getByText('Stressed', { exact: true })).toBeVisible()
  await expect(page.getByText('Deltas', { exact: true })).toBeVisible()
  await expect(page.getByText('Narrative', { exact: true })).toBeVisible()

  const body = await page.locator('body').innerText()
  expect(body).toMatch(/monthly_surplus|total_shortfall|weighted_goal_achievement|income/i)
})

test('navigates from home to the plan through the app shell', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'My plan', exact: true }).click()
  await expect(page).toHaveURL(/\/optimize/)
  await expect(page.getByRole('heading', { name: 'Your plan' })).toBeVisible()
})
