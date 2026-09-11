// Regression test for ERPlora/hub#1250 — contrato VISUAL del shell, pantalla ajustes.
//
// `/settings` sin hash aterriza en la pestaña «Hub» (`resolveSettingsTab('')`, `SettingsPage.vue`):
// país, huso horario, moneda e idioma del hub del seed de dev — ninguno depende de módulos
// instalados, así que la pantalla es determinista con el hub vacío del banco de e2e.
import { test, expect } from '../bench-boot';
import { VIEWPORTS, freezeVisualClock, loggedInSession, skipIfBaselineMissingLocally, visualSnapshotMask, waitForVisualSettle } from './shell-visual-helpers';

test.describe('contrato visual del shell — ajustes', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`la pestaña «Hub» de Ajustes se pinta igual a ${width}px (hub#1250)`, async ({ page }, testInfo) => {
      const snapshot = `settings-${width}.png`;
      skipIfBaselineMissingLocally(testInfo, snapshot);

      await freezeVisualClock(page);
      await page.setViewportSize({ width, height });
      await loggedInSession(page);
      await page.goto('/settings');

      // Punto de asentamiento por CLASE: el tabbar del footer (montado siempre, fuera del
      // `v-if`/`v-else-if` por pestaña) y la primera tarjeta de la pestaña «Hub».
      await expect(page.locator('.ok-tabbar')).toBeVisible();
      await expect(page.locator('ion-card').first()).toBeVisible();

      // Y el shell ha TERMINADO: el botón de menú ya ha aparecido (o el sidebar ocupa su sitio)
      // y los iconos tienen su glifo. Las dos cosas llegan tarde y la pantalla pasa por aquí a
      // medio hacer en más de la mitad de las cargas (hub#1823).
      await waitForVisualSettle(page);

      // El QR del sidebar codifica el puerto del banco, que cambia en cada corrida desde
      // hub#1812: se TAPA, no se compara (`visualSnapshotMask`, hub#1752).
      await expect(page).toHaveScreenshot(snapshot, { mask: visualSnapshotMask(page) });
    });
  }
});
