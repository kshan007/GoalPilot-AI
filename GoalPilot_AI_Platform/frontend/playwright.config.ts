import { defineConfig, devices } from '@playwright/test'

/**
 * Browser-level acceptance tests.
 *
 * The suite assumes the API (127.0.0.1:8000) and the Vite dev server (localhost:5173) are already
 * running — see docs/DEMO_GUIDE.md. Keeping the servers external means the suite never fights the
 * developer for ports and can run against a deployed instance by overriding the two URLs.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 150_000,
  expect: { timeout: 25_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.UI_URL ?? 'http://localhost:5173',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
