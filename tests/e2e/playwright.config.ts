// Browser PoC of phase 1 (plan §8): Ioan's Chrome, hidden by default; `E2E_HEADED=1` shows it, slowed
// down so it can be followed.
// It drives the dev stack that `manage.py runserver` serves (Django on :8000 + Vite on :5173):
// start it first. One worker: the specs share that server and some of them restart it.
//
// Each run writes into its own folder, `.artifacts/test-results/<PW_RUN_ID>/` (traces, failure
// screenshots and `results.json`, the JSON report), so a run never wipes another's evidence:
// Playwright empties `outputDir` when a run starts, and two sessions may run the suite at once.
// `PW_RUN_ID` is fixed by the first evaluation of this file, in the runner: Playwright evaluates it
// again in every worker process, which inherits the runner's environment and so the same id.
// `E2E_OUTPUT_DIR` overrides the folder. The specs' own evidence keeps its fixed paths
// (`.artifacts/*.png` and `.artifacts/metrics/*.json`, from `shot()` and `record()` in helpers.ts);
// `.artifacts/results.json`, cited by the PoC report of 2026-10-13, is that run's and no longer
// rewritten.
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

const HERE = dirname(fileURLToPath(import.meta.url));

/** `20261013-220531-123-4242`: local time to the millisecond and the runner's pid. */
function newRunId(now: Date): string {
  const pad = (n: number, width = 2) => String(n).padStart(width, '0');
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `${date}-${time}-${pad(now.getMilliseconds(), 3)}-${process.pid}`;
}

process.env.PW_RUN_ID ??= newRunId(new Date());
const OUTPUT_DIR = resolve(process.env.E2E_OUTPUT_DIR ?? join(HERE, '.artifacts', 'test-results', process.env.PW_RUN_ID));

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: OUTPUT_DIR,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['json', { outputFile: join(OUTPUT_DIR, 'results.json') }]],
  use: {
    baseURL: 'http://a.localhost:8000',
    channel: 'chrome',
    headless: process.env.E2E_HEADED !== '1',
    launchOptions: { slowMo: process.env.E2E_HEADED === '1' ? 150 : 0 },
    viewport: { width: 1280, height: 860 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
