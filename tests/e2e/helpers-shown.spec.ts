// flow: ninguno — FIX de la infraestructura e2e: con un diálogo abierto, `shown(page)` es el diálogo
// `shown(page)` is the page on view, never a dialog presented over it: Ionic Vue wraps an inline
// `ion-modal`'s content in an `.ion-page` and moves the presented modal to `ion-app`, after the pages, so a
// helper that took the last visible `.ion-page` landed inside the dialog. There the list has no rows, and a
// spec that counted 0 rows after confirming a dialog passed before anything was deleted. Nor is it `ion-app`,
// which Ionic also marks `.ion-page` and which holds the route's page and the presented dialogs.
import { expect, type Page, test } from '@playwright/test';

import { A, api, createItem, listReady, login, openApps, rowOf, shot, shown, uniqueName } from './helpers';

const OVERLAYS = 'ion-modal, ion-popover, ion-alert, ion-action-sheet, ion-loading, ion-toast, ion-picker-legacy';

/** Where `shown(page)` lands: its parent, the overlay around it (if any) and whether it holds the list's rows. */
const landing = (page: Page) =>
  shown(page).evaluate(
    (el, overlays) => ({
      parent: el.parentElement?.tagName ?? null,
      overlay: el.closest(overlays)?.tagName ?? null,
      rows: el.querySelectorAll('[data-testid=demo-items-row]').length > 0,
    }),
    OVERLAYS,
  );

/** The route's page: the one `IonRouterOutlet` shows, with the list, outside any overlay. */
const ROUTE_PAGE = { parent: 'ION-ROUTER-OUTLET', overlay: null, rows: true };

const VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '834', width: 834, height: 1112 },
  { label: '390', width: 390, height: 844 },
];

test('with a dialog open, shown(page) is still the page under it, with its rows', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Under a dialog'));
  try {
    await page.goto('/demo/items');
    await listReady(page);
    await expect(rowOf(page, item.id)).toHaveCount(1);
    expect(await landing(page), 'shown(page) is the route page').toEqual(ROUTE_PAGE);

    const sheet = await openApps(page);
    await expect(sheet).toBeVisible();
    // The item still exists, so a count of 0 cannot pass while the dialog is open.
    await expect(rowOf(page, item.id)).toHaveCount(1);
    expect(await landing(page), 'with the dialog open, shown(page) is still the route page').toEqual(ROUTE_PAGE);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(rowOf(page, item.id)).toHaveCount(1);
      // Two frames: Ionic lays the sheet and the page out again after the resize.
      await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
      await page.screenshot({ path: shot(`FIX-HUB-E2E-SHOWN-DIALOG-${viewport.label}`) });
    }
  } finally {
    const res = await api(context, A, 'POST', '/demo/items/delete', { id: item.id });
    expect(res.status).toBeLessThan(300);
  }
});
