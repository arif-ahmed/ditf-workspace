import { defineConfig, devices } from '@playwright/test';

// Local dev stack only (docs/local-dev.md). Output goes to the git-ignored reports\client folder.
export default defineConfig({
  testDir: './specs',
  fullyParallel: false,
  workers: 1, // one case after another: the cases create real rows (agents, coupons, ...) in the dev database
  timeout: 90_000,
  expect: { timeout: 10_000 },
  outputDir: '../../reports/client/artifacts',
  reporter: [
    ['list'],
    ['html', { outputFolder: '../../reports/client/html', open: 'never' }],
    ['json', { outputFile: '../../reports/client/results.json' }],
  ],
  use: {
    baseURL: process.env.CLIENT_URL ?? 'http://localhost:5000',
    screenshot: 'on',
    video: 'on', // every case is recorded and embedded in the HTML report
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 850 } } }],
});
