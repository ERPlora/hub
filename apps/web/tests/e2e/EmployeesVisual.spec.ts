// Regression test for ERPlora/hub#1250 — contrato VISUAL del shell, pantalla personal.
//
// `/employees` sin hash aterriza en la pestaña «Personal» (`tab = ref<EmployeeTab>(... ?? 'staff')`,
// `EmployeesPage.vue`): la lista de `hub_user` del seed de dev (solo el usuario Demo) — no depende
// de ningún módulo de negocio, así que es determinista con el hub vacío del banco de e2e.
import { test, expect } from '../bench-boot';
import { VIEWPORTS, freezeVisualClock, loggedInSession, skipIfBaselineMissingLocally } from './shell-visual-helpers';

test.describe('contrato visual del shell — personal', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`la pestaña «Personal» se pinta igual a ${width}px (hub#1250)`, async ({ page }, testInfo) => {
      const snapshot = `employees-${width}.png`;
      skipIfBaselineMissingLocally(testInfo, snapshot);

      await freezeVisualClock(page);
      await page.setViewportSize({ width, height });
      await loggedInSession(page);
      await page.goto('/employees');

      // Punto de asentamiento por CLASE: el tabbar del footer y la tabla de personal
      // (`<ok-data-table>` solo se monta en la rama `v-else` de `EmployeesPage.vue`, tras el
      // spinner de carga — esperarla es esperar a que la carga haya terminado, sin mirar texto).
      await expect(page.locator('.ok-tabbar')).toBeVisible();
      await expect(page.locator('ok-data-table').first()).toBeVisible();

      await expect(page).toHaveScreenshot(snapshot);
    });
  }
});
