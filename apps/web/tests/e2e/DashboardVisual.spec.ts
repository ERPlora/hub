// Regression test for ERPlora/hub#1250 — contrato VISUAL del shell, pantalla dashboard.
//
// Segunda pantalla del contrato tras el login (hub#1240): un hub VACÍO (sin módulos instalados,
// `HUB_MODULES_DIR` apunta a un directorio temporal — ver `tests/playwright.config.ts`) aterriza
// directo en /dashboard sin desvío a ningún «first-run» (decisión del humano 2026-07-12, ver
// `DashboardPage.spec.ts`). Ese estado vacío es justo lo que hace la captura determinista: sin
// módulos no hay widgets de negocio que varíen entre corridas, solo el widget CORE de
// export/import, que vive dentro de `<ok-widget-board>` en todos los presets por defecto.
import { test, expect } from '@playwright/test';
import { VIEWPORTS, loggedInSession, skipIfBaselineMissingLocally } from './shell-visual-helpers';

test.describe('contrato visual del shell — dashboard', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`el dashboard de un hub vacío se pinta igual a ${width}px (hub#1250)`, async ({ page }, testInfo) => {
      const snapshot = `dashboard-${width}.png`;
      skipIfBaselineMissingLocally(testInfo, snapshot);

      await page.setViewportSize({ width, height });
      await loggedInSession(page);
      await page.goto('/dashboard');

      // Punto de asentamiento por CLASE, nunca por texto (ADR-0055, la pantalla está traducida):
      // el board de widgets (`<ok-widget-board>`) es el contenedor DENTRO del que vive el widget
      // core de export/import (`DashboardPage.spec.ts`), y su montaje marca que Ionic ya hidrató.
      await expect(page.locator('ok-widget-board')).toBeVisible();

      // `fullPage` NO: en Ionic el scroll vive dentro de `ion-content` (mismo criterio que login).
      await expect(page).toHaveScreenshot(snapshot);
    });
  }
});
