// flow: SALE-F10
// hub#2009: a product sold by weight takes a typed quantity with up to three decimals, and its line's quantity field
// shows it whole next to its unit («0,532 kg»). The field was a fixed 2.3rem and cut the last digit («0,53» with half
// a «2» under «kg»), the only place the line shows the weight. In Spanish, on a desktop, a tablet standing up and a
// phone; what a run creates, its product `E2E-WEIGHT-<run>` and its check, is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, saveSessionForTheSweep, shown } from './helpers';
import { createProduct, type Product } from './inventory-helpers';
import { cleanTill, drawerOff, openTillCart, stamp, tillIn, tillIsPhone } from './sale-helpers';

const KEY = 'FIX-HUB-2009-WEIGHT-QTY';
const RUN = stamp();
const SIZES = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
] as const;
/** What is typed, what the field then holds and what the line charges at 24,00 € the kilo. */
const WEIGHTS = [
  { typed: '0,532', shown: '0,532', amount: /12,77\s€/ },
  { typed: '12,345', shown: '12,345', amount: /296,28\s€/ },
] as const;

let product: Product;
let context: BrowserContext;
let page: Page;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const setup = await browser.newContext({ baseURL: A });
  const setupPage = await setup.newPage();
  await login(setupPage, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(setup);
  product = await createProduct(setup, {
    name: `E2E Prawns ${RUN}`,
    sku: `E2E-WEIGHT-${RUN}`,
    price: 2400,
    unit: 'kg',
    pricing_unit: 'kg',
  });
  await setup.close();
  context = await browser.newContext({ baseURL: A, locale: 'es-ES', viewport: SIZES[0] });
  page = await context.newPage();
  await tillIn(page, context, 'es');
  await saveSessionForTheSweep(context);
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
  await expect(line()).toBeAttached();
});

test.afterAll(async () => {
  await context?.close();
  cleanTill();
});

const line = (): Locator => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first();

/** The quantity typed into the line's field and confirmed, once the server has valued it and the check's total too
 *  (a dash while its preview is on its way). On a phone the line scrolls under «Send order»: brought into view. */
async function weigh(weight: (typeof WEIGHTS)[number]): Promise<void> {
  await openTillCart(page);
  const field = line().locator('.pos-qty__field');
  await field.scrollIntoViewIfNeeded();
  await field.fill(weight.typed);
  await field.press('Enter');
  await expect(line()).toContainText(weight.amount);
  await expect(field).toHaveValue(weight.shown);
  await expect(shown(page).locator('[data-testid=pos-total]')).toHaveText(weight.amount);
  await field.evaluate((el) => el.scrollIntoView({ block: 'center' }));
}

/** The field's figure whole inside it, the unit after it, and the selector inside its line. */
async function quantityReadsWhole(weight: (typeof WEIGHTS)[number], where: string): Promise<void> {
  const fit = await line().evaluate((row) => {
    const field = row.querySelector('.pos-qty__field') as HTMLInputElement;
    const unit = row.querySelector('[data-testid=pos-qty-unit]') as HTMLElement;
    const stepper = row.querySelector('.pos-qty') as HTMLElement;
    const label = row.querySelector('.pos-line__label') as HTMLElement;
    const box = (el: Element) => el.getBoundingClientRect();
    return {
      value: field.value,
      content: field.scrollWidth,
      room: field.clientWidth,
      fieldRight: box(field).right,
      unitLeft: box(unit).left,
      unitText: unit.textContent?.trim(),
      stepperRight: box(stepper).right,
      lineRight: box(row).right,
      labelWidth: box(label).width,
    };
  });
  expect(fit.value, `the field at ${where}`).toBe(weight.shown);
  expect(fit.content, `«${weight.shown}» whole inside its field at ${where}`).toBeLessThanOrEqual(fit.room);
  expect(fit.unitText, `the unit at ${where}`).toBe('kg');
  expect(fit.unitLeft, `the unit after the figure at ${where}`).toBeGreaterThanOrEqual(fit.fieldRight - 0.5);
  expect(fit.stepperRight, `the selector inside its line at ${where}`).toBeLessThanOrEqual(fit.lineRight + 0.5);
  expect(fit.labelWidth, `the product's name keeps its room at ${where}`).toBeGreaterThan(40);
}

for (const weight of WEIGHTS) {
  test(`SALE-F10: «${weight.typed} kg» reads whole in its line on a desktop, a tablet and a phone`, async () => {
    for (const size of SIZES) {
      const where = `${size.label} with ${weight.typed}`;
      await page.setViewportSize({ width: size.width, height: size.height });
      await tillIsPhone(page);
      await weigh(weight);
      await quantityReadsWhole(weight, where);
      await capture(page, `${KEY}-${weight.shown.replace(',', '_')}-${size.label}`);
      if (await tillIsPhone(page)) {
        await shown(page).locator('[data-testid=pos-cart-close]').click();
        await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
      }
    }
  });
}
