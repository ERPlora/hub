// hub#2255 — with the hub REFUSING every request (the empty 403 of an edge ban, infra#334), the app
// says the business is not available and that this device has nothing to check, instead of «check
// your internet connection»; and it lets the person in by itself once the hub answers again.
//
// Bench spec, not only a unit test: the notice is painted into `#app` before the shell mounts, by
// the real `main.ts`, with the real Ionic and OutfitKit — the path a unit test stubs out.
import { expect, test } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

const REFUSED_RETRY_MS = 30_000;

test.describe('a hub that refuses at boot is not blamed on the device (hub#2255)', () => {
  for (const viewport of VIEWPORTS) {
    test(`at ${viewport.width}px: «not available», no connection advice, and in by itself once it answers`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.clock.install();
      await loggedInSession(page);
      // Every call to the hub answers what the edge answered on 27/09: 403, empty body.
      const refuse = (route: import('@playwright/test').Route) => route.fulfill({ status: 403, body: '' });
      await page.route(/\/api\//, refuse);

      await page.goto('/apps');

      const notice = page.getByTestId('boot-unreachable');
      await expect(notice).toHaveAttribute('data-failure', 'refused');
      await expect(page.getByText('Tu negocio no está disponible ahora mismo')).toBeVisible();
      await expect(page.getByText(/no tienes que revisar nada/)).toBeVisible();
      await expect(page.getByText(/conexión a Internet/)).toHaveCount(0);
      await expect(page.getByTestId('boot-unreachable-retry')).toBeVisible();
      // The whole notice fits the screen: nothing to scroll sideways to reach the button.
      const box = await page.getByTestId('boot-unreachable-retry').boundingBox();
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);

      // The hub is back: without touching anything, the next automatic try lets the person in.
      await page.unroute(/\/api\//, refuse);
      await page.clock.runFor(REFUSED_RETRY_MS);
      await expect(notice).toHaveCount(0);
      await expect(page).toHaveURL(/\/apps$/);
      await expect(page.locator('ion-router-outlet .ion-page:not(.ion-page-hidden)').first()).toBeVisible();
    });
  }
});
