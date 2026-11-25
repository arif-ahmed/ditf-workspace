import { defineConfig, devices } from '@playwright/test';

// Local dev stack only (docs/local-dev.md). Output goes to the git-ignored reports\web folder.
export default defineConfig({
  testDir: './specs',
  fullyParallel: false,
  workers: 1, // one case after another: the pay cases create real bookings in the dev database
  timeout: 90_000,
  expect: { timeout: 10_000 },
  outputDir: '../../reports/web/artifacts',
  reporter: [
    ['list'],
    ['html', { outputFolder: '../../reports/web/html', open: 'never' }],
    ['json', { outputFile: '../../reports/web/results.json' }],
  ],
  use: {
    baseURL: process.env.WEB_URL ?? 'http://localhost:4200',
    screenshot: 'on',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } } }],
});
