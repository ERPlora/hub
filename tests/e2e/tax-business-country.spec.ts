// flow: TAX-F17, TAX-F18, TAX-F19 (hub#996)
// A business erplora.com registered in Portugal (`PUT /internal/hubs/{id}`, signed as the SaaS sends it): Taxes never
// charges it with Spain's factory rules, which its database still keeps (TAX-F16). On the Home «Your taxes» is pending
// and «Important»; above the tax lists it says that Portugal brings no factory rates and that they are created in Rules,
// in English and in Spanish; the till refuses a product of the generic category with the reason in sight and charges
// nothing. Seen at 375×667, 768×1024 and 1440×900 (`HUB-996-notice-<width>.png`, `HUB-996-notice-es-<width>.png`,
// `HUB-996-refusal-<width>.png`). What the run makes is deleted after it, and `a` goes back to its own country.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, stamp } from './sale-helpers';
import { horizontalOverflow } from './tax-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'HUB-996';
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '768', width: 768, height: 1024 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const RUN = stamp();
const NOTICE_EN =
  'Portugal does not come with its tax rates ready: create in Rules the rate of each category you sell so the till can price a sale.';
const NOTICE_ES =
  'Portugal no trae sus tipos de impuesto de fábrica: crea en Reglas el tipo de cada categoría que vendes para que el TPV pueda calcular el precio de una venta.';

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let shirt: Product;

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/tax/categories');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  // A factory category: Spain's 21 % VAT is in the business's database, and no rule of Portugal.
  shirt = await createProduct(context, { name: `E2E Shirt PT ${RUN}`, sku: `E2E-PT-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  await context.close();
  await registerBusinessIn(original, 'PT');
});

test.afterAll(async () => {
  try {
    if (original) await registerBusinessIn(original, original.country);
  } finally {
    cleanSales();
    cleanInventory();
    restoreDrawer();
  }
});

const notice = (page: Page): Locator => shown(page).locator('[data-testid=tax-setup]');

async function inSpanish(context: BrowserContext, page: Page, path: string): Promise<void> {
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${path}`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
}

test(`${KEY} TAX-F17: «Your taxes» says Portugal brings no factory rates and leads to Rules, on the Home and in Taxes`, async ({ page }) => {
  await login(page, A, '/');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const card = shown(page).locator('[data-testid="setup-card"]');
  await expect(card).toHaveAttribute('aria-busy', 'false');
  const toggle = card.locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'View all') await toggle.click();
  // Spain's eleven factory rules are no use to a business in Portugal: the step stays pending and important.
  const step = card.locator('[data-testid="setup-row"][data-key="tax.rules"]');
  await expect(step.locator('[data-testid="setup-pill"]')).toHaveText('Important');

  await page.goto(`${A}/tax/categories`);
  await expect(notice(page)).toContainText('Your taxes');
  await expect(notice(page)).toContainText(NOTICE_EN);
  // The rate column says what a sale would be charged: nothing, never Spain's 21 %.
  const generic = shown(page).locator('[data-testid=tax-categories-row]').filter({ hasText: 'Product — generic' });
  await expect(generic).not.toContainText('21');
  for (const vp of SIZES) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(notice(page), `notice at ${vp.label}`).toBeInViewport();
    await expect.poll(() => horizontalOverflow(page), `categories at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`${KEY}-notice-${vp.label}`) });
  }
  await shown(page).locator('[data-testid=tax-setup-action]').click();
  await expect(page).toHaveURL(`${A}/tax/rules`);
  await expect(notice(page)).toContainText(NOTICE_EN);
});

test(`${KEY} TAX-F17: in Spanish, «Tus impuestos» says the same`, async ({ page, context }) => {
  await login(page, A, '/tax/categories');
  await inSpanish(context, page, '/tax/categories');
  await expect(notice(page)).toContainText('Tus impuestos');
  await expect(notice(page)).toContainText(NOTICE_ES);
  for (const vp of SIZES) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(notice(page), `notice at ${vp.label}`).toBeInViewport();
    await expect.poll(() => horizontalOverflow(page), `categories at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`${KEY}-notice-es-${vp.label}`) });
  }
});

test(`${KEY} TAX-F19: the till of a business in Portugal never charges Spain's VAT, and says why`, async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toHaveText('—');

  // «Charge»: the server's reason, in sight, and nothing to confirm.
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  const refusal = sheet.locator('[data-testid=sale-checkout-read-error]');
  await expect(refusal).toContainText(`«${shirt.name}» cannot be charged: no tax rule applies to its tax category`);
  await expect(sheet.locator('[data-testid=sale-checkout-confirm]')).toHaveAttribute('aria-disabled', 'true');
  await expect(sheet).not.toContainText(/12[.,]10/);
  for (const vp of SIZES) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(refusal, `refusal at ${vp.label}`).toBeInViewport();
    await expect.poll(() => horizontalOverflow(page), `checkout at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`${KEY}-refusal-${vp.label}`) });
  }

  // Server-side evidence: nothing was charged, at Spain's VAT or at anything else.
  await expect(newestSaleOf(context, shirt.sku)).rejects.toThrow(`no recent sale sold ${shirt.sku}`);
});
