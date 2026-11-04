// flow: SALE-F38 and SALE-F07 (apps/sale/WORKBOOK.md) — a service without a tax category says why it cannot be
// sold when tapped in the till and adds nothing. That notice goes on its own as soon as the service has its category,
// with no other tap: from another device or the assistant, with the till open all along, and on leaving the till for
// Services and coming back (hub#719). Screenshots of the till in the three viewports. What this file creates is
// deleted after it.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { drawerOff, restoreDrawer, stamp, tillIsPhone } from './sale-helpers';
import { cleanUp, FLOW_VIEWPORTS, named, post } from './service-helpers';

const RUN = stamp();
const GENERIC = 'service.generic';

/** Its tile. Without VAT it looks blocked (`aria-disabled`) and still takes the tap: `force`, or Playwright waits for it. */
const tile = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=pos-service-${id}]`);
const notice = (page: Page): Locator => shown(page).locator('[data-testid=pos-tap-notice]');
const SAID = /^(Cannot be sold: no tax category\.|No se puede vender: sin categoría fiscal\.)/;

/** A service with no tax category: the API refuses to create one (`service.tax_category_required`), but the catalogue
 *  has them (imported, or from before the rule), and the till and Services both handle them. */
async function untaxedService(context: Parameters<typeof post>[0], label: string): Promise<{ id: string; name: string }> {
  const name = named(`${label} ${RUN}`);
  const { id } = await post<{ id: string }>(context, '/service/services', { name, price: 2500, tax_category_key: GENERIC });
  psql(`update service_service set tax_category_id = null where id = '${id}'`);
  return { id, name };
}

async function giveTaxCategory(context: Parameters<typeof post>[0], id: string): Promise<void> {
  const res = await api(context, A, 'POST', '/service/services/update', { id, tax_category_key: GENERIC });
  expect(res.status, JSON.stringify(res.data)).toBe(200);
}

/** The till on its «Services» chip, with the service on it. */
async function tillOnServices(page: Page, id: string): Promise<void> {
  await page.goto(`${A}/sale/pos`);
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-category-services]').click();
  await tile(page, id).waitFor({ state: 'visible' });
}

/** Opens `path` from inside the Hub, as one of its links does: the SPA's router, no page load (Ionic keeps the
 *  till mounted under the screen it opens, and brings that same till back). */
async function openInside(page: Page, path: string): Promise<void> {
  type Mounted = { __vue_app__: { config: { globalProperties: { $router: { push: (to: string) => Promise<unknown> } } } } };
  await page.evaluate(
    (to) => (document.querySelector('#app') as unknown as Mounted).__vue_app__.config.globalProperties.$router.push(to),
    path,
  );
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await context.close();
});

test.afterAll(() => {
  cleanUp();
  restoreDrawer();
});

test('SALE-F38 (hub#719): the notice of a service without VAT goes on its own once it has a category', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const service = await untaxedService(context, 'Corte');
  await tillOnServices(page, service.id);
  await tile(page, service.id).click({ force: true });
  await expect(notice(page)).toHaveText(SAID);

  // Another device, or the assistant, gives it its category: the till hears it, and the notice goes without another
  // tap; nothing went into the check, and the service can be sold now.
  await giveTaxCategory(context, service.id);
  await expect(notice(page)).toBeHidden();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: service.name })).toHaveCount(0);
  for (const size of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(tile(page, service.id)).toBeVisible();
    // On a phone the check becomes a drawer that slides away (0.25 s): the shot waits until it is gone.
    if (await tillIsPhone(page)) await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
    await capture(page, `HUB-719-taxed-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await tile(page, service.id).click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: service.name })).toHaveCount(1);
  await expect(notice(page)).toBeHidden();
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

test('SALE-F38 (hub#719): off to Services for the category and back to the till, the notice is not there', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const service = await untaxedService(context, 'Color');
  await tillOnServices(page, service.id);
  await tile(page, service.id).click({ force: true });
  await expect(notice(page)).toHaveText(SAID);

  await openInside(page, '/service/services');
  await expect(shown(page).locator('[data-testid=pos-till]')).toHaveCount(0);
  await giveTaxCategory(context, service.id);
  await openInside(page, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await expect(tile(page, service.id)).toBeVisible();
  await expect(notice(page)).toHaveCount(0);
});

test('SALE-F38 (hub#719): while it still has no category, the notice stays', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const service = await untaxedService(context, 'Peinado');
  await tillOnServices(page, service.id);
  await tile(page, service.id).click({ force: true });
  await expect(notice(page)).toHaveText(SAID);
  // Something else about it changes: the follower hears it, and the reason still holds.
  const renamed = await api(context, A, 'POST', '/service/services/update', { id: service.id, name: `${service.name} v2` });
  expect(renamed.status, JSON.stringify(renamed.data)).toBe(200);
  await expect(tile(page, service.id)).toContainText('v2');
  await expect(notice(page)).toHaveText(SAID);
});
