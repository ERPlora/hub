// Regression test for ERPlora/hub#1250 — contrato VISUAL del shell, pantalla apps (marketplace).
//
// `/apps` aterriza por defecto en la pestaña «Mis apps» (`tab = ref<AppsTab>(... ?? 'mine')`,
// `AppsPage.vue`), que lee del runtime LOCAL (`listInstalledModules`) — determinista, no depende
// del Cloud. El catálogo remoto sí se pide en `onMounted` (`loadCatalog()`), pero el banco de e2e
// apunta `HUB_CLOUD_API_URL` a un puerto cerrado (`playwright.config.ts`) para no depender de la
// red, y el aviso de error de esa llamada solo se pinta cuando `tab !== 'mine'`
// (`v-if="catalogError && tab !== 'mine'"`) — así que en la pestaña por defecto es invisible y no
// puede colar ruido en la captura.
import { test, expect } from '../bench-boot';
import { VIEWPORTS, freezeVisualClock, loggedInSession, skipIfBaselineMissingLocally, visualSnapshotMask, waitForVisualSettle } from './shell-visual-helpers';

test.describe('contrato visual del shell — apps', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`la pestaña «Mis apps» de un hub vacío se pinta igual a ${width}px (hub#1250)`, async ({ page }, testInfo) => {
      const snapshot = `apps-${width}.png`;
      skipIfBaselineMissingLocally(testInfo, snapshot);

      await freezeVisualClock(page);
      await page.setViewportSize({ width, height });
      await loggedInSession(page);
      await page.goto('/apps');

      // Punto de asentamiento por CLASE: el tabbar del footer (siempre montado, fuera de los
      // `v-show` de pestaña) y la tabla de «Mis apps» (`<ok-data-table>`, primera del DOM).
      await expect(page.locator('.ok-tabbar')).toBeVisible();
      await expect(page.locator('ok-data-table').first()).toBeVisible();

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
