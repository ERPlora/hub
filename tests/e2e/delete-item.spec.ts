// DEMO-F03 (and the «borra» of DEMO-F05): «Delete» on the detail asks first; «Cancel» keeps the
// item, «Delete» removes it and goes back to the list without its row, and another tab with the
// same detail open says «This item no longer exists.» by itself.
import { expect, test } from '@playwright/test';

import { A, api, createItem, listReady, login, record, rowOf, shot, shown, uniqueName } from './helpers';
import { recordResponses, responseEnd } from './resource-timing';

test('delete asks first; cancel keeps it; confirm removes it here and the other tab says it no longer exists', async ({ context }) => {
  const tab1 = await context.newPage();
  await recordResponses(tab1);
  await login(tab1, A);
  const item = await createItem(context, A, uniqueName('To delete'));
  const tab2 = await context.newPage();
  await tab2.goto(`/demo/items/${item.id}`);
  await tab1.goto('/demo/items');
  await listReady(tab1);
  await rowOf(tab1, item.id).click();
  await expect(shown(tab1).locator('[data-testid=demo-detail-status]')).toBeVisible();
  await expect(shown(tab2).locator('[data-testid=demo-detail-status]')).toBeVisible();

  // Cancel: nothing happens.
  await shown(tab1).locator('[data-testid=demo-detail-delete]').click();
  const alert = tab1.locator('ion-alert');
  await expect(alert).toBeVisible();
  const header = (await alert.locator('.alert-title').innerText()).trim();
  await tab1.screenshot({ path: shot('delete-item--confirm') });
  await alert.locator('button', { hasText: 'Cancel' }).click();
  await expect(alert).toBeHidden();
  const afterCancel = await api(context, A, 'GET', `/demo/items/detail?id=${item.id}`);

  // Confirm: back to the list without the row; the other tab is told. Times are taken in the pages
  // (slowMo delays every Playwright step): when tab 2 paints the message, against tab 1's click and
  // the end of its delete request.
  await tab2.evaluate(() => {
    const w = window as unknown as { __toldAt?: number };
    const observer = new MutationObserver(() => {
      if (document.querySelector('[data-testid=demo-detail-error]')?.textContent?.includes('no longer exists')) {
        w.__toldAt = Date.now();
        observer.disconnect();
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await shown(tab1).locator('[data-testid=demo-detail-delete]').click();
  await expect(alert).toBeVisible();
  const confirm = alert.locator('button.alert-button-role-destructive');
  await confirm.evaluate((el) =>
    el.addEventListener('click', () => ((window as unknown as { __clickedAt: number }).__clickedAt = Date.now()), { capture: true, once: true }),
  );
  await confirm.click();
  await expect(tab1).toHaveURL(/\/demo\/items$/);
  await listReady(tab1);
  await expect(rowOf(tab1, item.id)).toHaveCount(0);
  const gone = shown(tab2).locator('[data-testid=demo-detail-error]');
  await expect(gone).toContainText('This item no longer exists.', { timeout: 5000 });
  const toldAt = await tab2.evaluate(() => (window as unknown as { __toldAt?: number }).__toldAt);
  const clickedAt = await tab1.evaluate(() => (window as unknown as { __clickedAt?: number }).__clickedAt);
  expect(toldAt, 'tab 2 timed «This item no longer exists.»').toBeDefined();
  expect(clickedAt, 'tab 1 timed the click on «Delete»').toBeDefined();
  // Read from the recorder: Vite's dev modules fill the page's resource timing buffer before the click.
  const deletedAt = (await responseEnd(tab1, '/api/demo/items/delete')).epochMs;
  const otherTabToldMs = toldAt! - clickedAt!;
  const responseToOtherTabMs = Math.round(toldAt! - deletedAt);
  await tab1.screenshot({ path: shot('delete-item--list-after') });
  await tab2.screenshot({ path: shot('delete-item--other-tab') });
  const afterDelete = await api(context, A, 'GET', `/demo/items/detail?id=${item.id}`);

  record('delete-item', {
    header,
    afterCancelStatus: afterCancel.status,
    afterDeleteStatus: afterDelete.status,
    clickToOtherTabMs: otherTabToldMs,
    responseToOtherTabMs,
  });
  expect(header).toBe('Delete this item and its lines?');
  expect(afterCancel.status).toBe(200);
  expect(afterDelete.status).toBe(404);
  // The request leaves when the alert has closed (its animation), so the bound is the request's end.
  expect(responseToOtherTabMs).toBeLessThan(1000);
});
