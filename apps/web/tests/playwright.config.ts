import { defineConfig, devices } from '@playwright/test';

// E2E del shell del Hub contra el runtime REAL (Axum :8787) y Vite (:5173). Sin mocks (regla del
// proyecto): el test arranca su propio runtime con BD efímera y un directorio de módulos VACÍO,
// que es exactamente el estado "hub recién creado" que queremos ejercer. Ver `e2e/README.md`.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.HUB_WEB_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
