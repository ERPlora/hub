// flow: service-business-currency (FIX-HUB-SERVICE-PRICE-STORED-IN-HUNDREDTHS-WHATEVER-THE-CURRENCY and
// FIX-HUB-SERVICE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/service/WORKBOOK.md «Antes de empezar»)
// Services writes, saves and paints its amounts in the business's currency: its country's, as erplora.com registered
// it (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), in that currency's minor units — the unit Sales
// charges —, never in hundredths of a fixed euro. Hub `a` moves to Japan: «New service» names the field «Price (JPY)»,
// «1500» is saved as 1500 yen (read back through the API) and the till charges it at ¥1,500, never ¥150,000, in 390, 834
// and 1440. In Poland the run's service and voucher read in złoty in the list (captures
// `FIX-HUB-SERVICE-PRICE-STORED-IN-HUNDREDTHS-WHATEVER-THE-CURRENCY-<width>`), the form names «Price (PLN)» and its two
// readings of «1.250» are in złoty, and «Packages» shows the voucher's closed price in złoty. Back in Spain, euros
// (`…-es-1440`). What the run creates is deleted after it and `a`'s registration put back, also when a test fails.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, hostPage, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { openTillCart } from './sale-helpers';
import { cleanUp as cleanServices, named, noHorizontalScroll, pick, post, settled } from './service-helpers';

const KEY = 'FIX-HUB-SERVICE-PRICE-STORED-IN-HUNDREDTHS-WHATEVER-THE-CURRENCY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** An amount in `symbol` as a till writes it, the symbol before or after the figure («22,50 zł», «zł 22.50»). */
const amount = (symbol: string, figure: string): RegExp => new RegExp(`${symbol}\\s?${figure}|${figure}\\s?${symbol}`);
const zloty = (figure: string): RegExp => amount('zł', figure);
const euros = (figure: string): RegExp => amount('€', figure);

/** The checks the till opened with this run's services (their lines name an `E2E Svc` service). */
const RUN_ORDERS =
  "select distinct order_id as id from sale_orderline where service_id in (select id from service_service where name like 'E2E Svc%')";

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
/** A service and a voucher of the run, priced through the API in minor units (22,50 and 90,00 in euros). */
let color = { id: '', name: '' };
let voucher = { id: '', name: '' };
/** The service the owner creates in Japan through the form. */
const YEN_SERVICE = named('Corte yen');

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanAll(): void {
  psql(
    [
      `create temp table e2e_svc_orders as ${RUN_ORDERS}`,
      'delete from sale_orderline where order_id in (select id from e2e_svc_orders)',
      'delete from customer_orderlink where order_id in (select id from e2e_svc_orders)',
      'delete from sale_order where id in (select id from e2e_svc_orders)',
    ].join('; '),
  );
  cleanServices();
}

async function call<T>(context: BrowserContext, path: string): Promise<T> {
  const res = await api<T>(context, A, 'GET', path);
  expect(res.status, `GET ${path} ${JSON.stringify(res.data)}`).toBe(200);
  return res.data;
}

/** The row of the service `id` in Services, found by its name. */
async function serviceRow(page: Page, id: string, name: string): Promise<Locator> {
  await login(page, A, '/service/services');
  await shown(page).locator('[data-testid=service-services-row], [data-testid=service-services-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=service-services-search] input').fill(name);
  const row = shown(page).locator(`[data-testid=service-services-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  return row;
}

/** The row of the run's voucher in «Packages». */
async function voucherRow(page: Page): Promise<Locator> {
  await login(page, A, '/service/packages');
  await shown(page).locator('[data-testid=service-packages-row], [data-testid=service-packages-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=service-packages-search] input').fill(voucher.name);
  const row = shown(page).locator(`[data-testid=service-packages-row][data-id="${voucher.id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanAll();
  const owner = await hostPage(browser, A, { next: '/service/services' });
  const colorName = named('Color');
  color = { id: (await post<{ id: string }>(owner.context, '/service/services', { name: colorName, price: 2250, tax_category_key: 'service.generic' })).id, name: colorName };
  const voucherName = named('Bono');
  const created = await post<{ id: string }>(owner.context, '/service/packages', { name: voucherName, fixed_price: 9000, max_uses: 5, items: [{ service_id: color.id, sessions: 5 }] });
  voucher = { id: created.id, name: voucherName };
  await owner.context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanAll();
});

test(`${KEY}: service-business-currency a business in Japan saves «1500» as 1500 yen and the till charges ¥1,500 in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'JP');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/service/services');
  const view = shown(page);
  await view.locator('[data-testid=service-services-empty], [data-testid=service-services-row]').first().waitFor({ state: 'visible' });
  await view.locator('[data-testid=service-services-add]').click();
  const price = page.locator('[data-testid=service-form-price]');
  await expect(price).toContainText('Price (JPY)');
  await page.locator('[data-testid=service-form-name] input').fill(YEN_SERVICE);
  await price.locator('input').fill('1500');
  await price.locator('input').blur();
  await expect(price.locator('input')).toHaveValue('1500');
  await pick(page, 'service-form-tax', 'generic', 'Service — generic');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-jp-form-1440`) });
  await page.locator('[data-testid=service-form-submit]').click();
  await expect(page.locator('ion-modal[data-testid=service-form]')).toBeHidden();

  // Saved in the yen's minor units, the unit Sales charges: 1500, never 150000.
  const [saved] = (await call<{ rows: { id: string; name: string; price: number }[] }>(context, `/service/services?search=${encodeURIComponent(YEN_SERVICE)}`)).rows;
  expect([saved.name, saved.price]).toEqual([YEN_SERVICE, 1500]);
  const row = await serviceRow(page, saved.id, YEN_SERVICE);
  await expect(row).toContainText('¥1,500');

  // The till: the service's tile and the check's total, ¥1,500.
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-category-services]').click();
  const tile = shown(page).locator(`[data-testid=pos-service-${saved.id}]`);
  await expect(tile).toContainText('¥1,500');
  await tile.click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: YEN_SERVICE }).first()).toBeVisible();
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openTillCart(page);
    const total = shown(page).locator('[data-testid=pos-total]');
    await expect(total, `till at ${size.name}`).toContainText('¥1,500');
    await expect(total, `till at ${size.name}`).not.toContainText('150,000');
    await settled(page);
    await noHorizontalScroll(page, `till ${size.name}`);
    await page.screenshot({ path: shot(`${KEY}-jp-pos-${size.name}`) });
  }
});

test(`${KEY}: service-business-currency a business in Poland reads its services and vouchers in złoty in 390, 834 and 1440`, async ({ page }) => {
  await registerBusinessIn(original, 'PL');
  const row = await serviceRow(page, color.id, color.name);
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(row, `Services at ${size.name}`).toContainText(zloty('22[.,]50'));
    await expect(row, `Services at ${size.name}`).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, `Services ${size.name}`);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
  }

  // The form: «Price (PLN)», its two decimals, and the two readings of «1.250» in złoty.
  await page.setViewportSize({ width: 1440, height: 900 });
  await row.click();
  const form = page.locator('ion-modal[data-testid=service-form]');
  await expect(form).toBeVisible();
  const price = form.locator('[data-testid=service-form-price]');
  await expect(price).toContainText('Price (PLN)');
  await expect(price).not.toContainText('€');
  const input = price.locator('input').first();
  await expect(input).toHaveValue('22.50');
  await input.fill('1.250');
  await input.blur();
  await expect(price).toContainText(/could be zł\s?1,250\.00 or zł\s?1\.25/);
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-form-1440`) });
  await form.locator('[data-testid=service-form-cancel]').click();
  await expect(form).toBeHidden();

  // A voucher: its closed price in złoty.
  const pkg = await voucherRow(page);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(pkg, `Packages at ${size.name}`).toContainText(zloty('90[.,]00'));
    await expect(pkg, `Packages at ${size.name}`).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, `Packages ${size.name}`);
    await page.screenshot({ path: shot(`${KEY}-packages-${size.name}`) });
  }
});

test(`${KEY}: service-business-currency back in Spain the services and vouchers are in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  const row = await serviceRow(page, color.id, color.name);
  await expect(row).toContainText(euros('22[.,]50'));
  await expect(row).not.toContainText('zł');
  await row.click();
  const form = page.locator('ion-modal[data-testid=service-form]');
  await expect(form.locator('[data-testid=service-form-price]')).toContainText('Price (EUR)');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
  await form.locator('[data-testid=service-form-cancel]').click();
  await expect(await voucherRow(page)).toContainText(euros('90[.,]00'));
});
