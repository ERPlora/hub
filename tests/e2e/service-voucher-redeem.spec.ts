// SERVICE-F21 «Gastar una sesión fuera del cobro» in Chrome (hub#1058), with the real Staff, Customers and Sales
// apps: a voucher of 5 haircuts charged at the till for 90.00 and granted saying its sale; in «Sold vouchers» the
// receptionist taps «Spend a session», the only service it covers comes chosen, she picks Ana from the team, sees
// «5 sessions left · 4 after this one» and spends it: the row drops to «1 used · 4 left» by itself and Ana's
// production in Sales rises by the session's worth (90.00 ÷ 5). A voucher with nothing left says why before
// anything is spent. The dialog is captured at the fleet's three sizes, without sideways scroll.
import { expect, type Locator, test } from '@playwright/test';

import { A, api, capture } from './helpers';
import { chargeByApi, cleanSales } from './sale-helpers';
import { cleanUp, named, noHorizontalScroll, ownerPage, pick, post, rowAction, settled, VIEWPORTS } from './service-helpers';

interface StaffTotal {
  staff_id: string;
  voucher_total: number;
  production_total: number;
}

function cleanAll(): void {
  cleanUp();
  cleanSales();
}

test.beforeAll(cleanAll);
test.afterAll(cleanAll);

test('Sold vouchers: a session spent outside the till, choosing the service and the professional', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/service/packages');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  // The fleet's three sizes (ui-clip-sweep.sh): desktop, tablet and a low phone; `reached` stays on screen at each.
  const atEachSize = async (name: string, reached: Locator): Promise<void> => {
    for (const [width, height] of [[1440, 900], [820, 1180], [375, 667]]) {
      await page.setViewportSize({ width, height });
      await settled(page);
      await noHorizontalScroll(page, `${name} ${width}x${height}`);
      await expect(reached).toBeInViewport();
      await capture(page, `${name}-${width}x${height}`);
    }
    await page.setViewportSize(VIEWPORTS.desktop);
  };
  const productionOf = async (staffId: string): Promise<number> => {
    const res = await api<{ rows: StaffTotal[] }>(context, A, 'GET', '/sale/sales/by_staff');
    expect(res.status).toBe(200);
    return res.data.rows.find((row) => row.staff_id === staffId)?.production_total ?? 0;
  };

  const cut = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named('Cut'),
    price: 2000,
    tax_category_key: 'service.generic',
  });
  const ana = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'López' });
  const lucia = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Lucía') });
  const marta = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Marta') });
  const bono = named('Bono');
  const voucher = await post<{ id: string }>(context, '/service/packages', { name: bono, max_uses: 5, items: [{ service_id: cut.id }] });
  // Charged at the till as an open line (SERVICE-F14) and granted saying its sale: its sessions are worth 18.00 each.
  const sold = await chargeByApi(context, {
    open_lines: [{ name: `e2e ${bono}`, unit_price: 9000, tax_category_key: 'service.generic' }],
    payments: [{ method: 'card' }],
  });
  const lucias = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: lucia.id, amount: 9000, sale_id: sold.id });
  // Marta's only shows the refusal: no sale of its own needed.
  const martas = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: marta.id, amount: 0 });
  await post(context, '/service/grants/adjust', { id: martas.id, uses_delta: -5, days_delta: 0, reason: 'e2e nothing left' }, 200);
  const before = await productionOf(ana.id);

  await rowAction(page, 'service-packages', voucher.id, 'grants');
  const sheet = page.locator('ion-modal[data-testid=service-grants]');
  const row = sheet.locator(`[data-testid=service-grants-row-${lucias.id}]`);
  await expect(row).toContainText('0 used · 5 left');
  await atEachSize('service-grants-redeem', sheet.locator(`[data-testid=service-grants-redeem-${lucias.id}]`));

  // A voucher with nothing left: the check says why, and nothing can be spent.
  await sheet.locator(`[data-testid=service-grants-redeem-${martas.id}]`).click();
  const dialog = page.locator('ion-modal[data-testid=service-grant-redeem]');
  await expect(dialog.locator('[data-testid=service-grant-redeem-refused]')).toContainText('This voucher has no sessions left.');
  await expect(dialog.locator('[data-testid=service-grant-redeem-submit]')).toHaveAttribute('aria-disabled', 'true');
  await dialog.locator('[data-testid=service-grant-redeem-cancel]').click();
  await expect(dialog).toBeHidden();

  // Lucía's: the only service it covers comes chosen; Ana is picked from the team.
  await sheet.locator(`[data-testid=service-grants-redeem-${lucias.id}]`).click();
  await expect(dialog.locator('[data-testid=service-grant-redeem-message]')).toContainText(lucia.name);
  await expect(dialog.locator('[data-testid=service-grant-redeem-service]')).toContainText(cut.name);
  await expect(dialog.locator('[data-testid=service-grant-redeem-balance]')).toHaveText('5 sessions left · 4 after this one');
  await pick(page, 'service-grant-redeem-member', ana.full_name.split(' ')[0], ana.full_name);
  await dialog.locator('[data-testid=service-grant-redeem-note] textarea').fill('Came only for her session');
  await atEachSize('service-grant-redeem', dialog.locator('[data-testid=service-grant-redeem-submit]'));
  await dialog.locator('[data-testid=service-grant-redeem-submit]').click();
  await expect(dialog).toBeHidden();

  // The row follows the live list; the session counts in Ana's production in Sales.
  await expect(row).toContainText('1 used · 4 left');
  await expect.poll(() => productionOf(ana.id)).toBe(before + 1800);
  await context.close();
});
