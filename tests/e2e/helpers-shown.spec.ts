// flow: ninguno — FIX de la infraestructura e2e: con un diálogo abierto, `shown(page)` es el diálogo
// `shown(page)` is the page on view, never a dialog presented over it: Ionic Vue wraps an inline
// `ion-modal`'s content in an `.ion-page` and moves the presented modal to `ion-app`, after the pages, so a
// helper that took the last visible `.ion-page` landed inside the dialog. There the list has no rows, and a
// spec that counted 0 rows after confirming a dialog passed before anything was deleted.
import { expect, test } from '@playwright/test';

import { A, createItem, listReady, login, openApps, rowOf, shot, shown, uniqueName } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test('with a dialog open, shown(page) is still the page under it, with its rows', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Under a dialog'));
  await page.goto('/demo/items');
  await listReady(page);
  await expect(rowOf(page, item.id)).toHaveCount(1);

  const sheet = await openApps(page);
  await expect(sheet).toBeVisible();
  // The item still exists, so a count of 0 cannot pass while the dialog is open.
  await expect(rowOf(page, item.id)).toHaveCount(1);
  const overlay = await shown(page).evaluate((el) =>
    el.closest('ion-modal, ion-popover, ion-alert, ion-action-sheet, ion-loading, ion-toast, ion-picker-legacy')?.tagName ?? null,
  );
  expect(overlay, 'shown(page) resolved inside an overlay').toBeNull();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(rowOf(page, item.id)).toHaveCount(1);
    await page.screenshot({ path: shot(`FIX-HUB-E2E-SHOWN-DIALOG-${viewport.label}`) });
  }
});
