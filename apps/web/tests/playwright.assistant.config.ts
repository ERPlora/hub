import { defineConfig, devices } from '@playwright/test';

const webPort = process.env.ASSISTANT_E2E_WEB_PORT ?? '5173';
const runtimePort = process.env.ASSISTANT_E2E_RUNTIME_PORT ?? '8787';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'AssistantToolLoop.spec.ts',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  timeout: 90_000,
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node e2e/support/assistant-stack.mjs',
    url: `http://127.0.0.1:${runtimePort}/healthz`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
