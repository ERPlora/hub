// Browser PoC of phase 1 (plan §8): Ioan's Chrome, visible and slowed down so it can be followed.
// It drives the dev stack that `manage.py runserver` serves (Django on :8000 + Vite on :5173):
// start it first. One worker: the specs share that server and some of them restart it.
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: './.artifacts/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['json', { outputFile: './.artifacts/results.json' }]],
  use: {
    baseURL: 'http://a.localhost:8000',
    channel: 'chrome',
    headless: false,
    launchOptions: { slowMo: 150 },
    viewport: { width: 1280, height: 860 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
