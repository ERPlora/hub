// flow: combo-business-currency (FIX-HUB-COMBO-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/combo/WORKBOOK.md «Antes de empezar»)
// Menus paints and reads the closed price and the supplements in the business's currency: its country's, as
// erplora.com registered it (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a`
// moves to Poland: Menus lists the run's menu in złoty and its builder shows the closed price and the hake's supplement
// in złoty, with no «€», in 390, 834 and 1440 (captures `FIX-HUB-COMBO-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`);
// editing the hake names the field «Supplement (PLN)» and «2,50 zł» is saved as 250 grosze, and «Edit details» names the
// field «Closed price (PLN)» and «14,50» is saved as 1450 (both read back through the API). Back in Spain the same menu
// reads in euros and the field says EUR (`…-es-1440`). What the run creates is deleted after it and `a`'s registration
// put back, also when a test fails.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, hostPage, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-COMBO-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const TAG = 'E2E CCUR';
const STAMP = Date.now().toString(36).toUpperCase();
const MENU = `${TAG} Menu ${STAMP}`;
const sku = (code: string): string => `E2E-CCUR-${STAMP}-${code}`;
/** An amount in `symbol` as a till writes it, the symbol before or after the figure («13,50 zł», «zł 13.50»), with
 *  its `sign` if it has one («+2,00 zł»). */
function amount(symbol: string, figure: string, sign = ''): RegExp {
  const signed = sign.replace('+', '\\+');
  return new RegExp(`${signed}\\s?${symbol}\\s?${figure}|${signed}${figure}\\s?${symbol}`);
}
const zloty = (figure: string, sign = ''): RegExp => amount('zł', figure, sign);
const euros = (figure: string, sign = ''): RegExp => amount('€', figure, sign);

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let menuId = '';
let hakeChoice = '';

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  const combos = `select id from combo_combo where name like '${TAG}%'`;
  const groups = `select id from combo_choicegroup where combo_id in (${combos})`;
  const products = `select id from inventory_product where sku like 'E2E-CCUR-%'`;
  psql(
    [
      `delete from combo_choiceoption where group_id in (${groups}) or product_id in (${products})`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where name like '${TAG}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like 'E2E-CCUR-%'`,
    ].join('; '),
  );
}

async function call<T>(context: BrowserContext, method: 'GET' | 'POST', path: string, body?: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, method, path, body);
  expect(res.status, `${method} ${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

interface Detail {
  id: string;
  price: number;
  groups: { name: string; options: { id: string; product_name: string; price_delta: number }[] }[];
}

const detail = (context: BrowserContext): Promise<Detail> => call<Detail>(context, 'GET', `/combo/combos/detail?combo=${encodeURIComponent(MENU)}`);

/** The run's row in Menus (found by the run's stamp). */
async function menuRow(page: Page): Promise<Locator> {
  await login(page, A, '/combo/menus');
  await shown(page).locator('[data-testid=combo-menus-row], [data-testid=combo-menus-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=combo-menus-search] input').fill(STAMP);
  const row = shown(page).locator(`[data-testid=combo-menus-row][data-id="${menuId}"]`);
  await expect(row).toBeVisible();
  return row;
}

/** «Edit details» of the run's row: a button of the row on a wide screen, in the row's menu on a narrow one. */
async function editDetails(page: Page): Promise<Locator> {
  const action = shown(page).locator(`[data-testid=combo-menus-row-${menuId}-edit]`);
  const menu = shown(page).locator(`[data-testid=combo-menus-row-${menuId}-menu]`);
  await action.or(menu).first().waitFor({ state: 'visible' });
  if (await action.isVisible()) await action.click();
  else {
    await menu.click();
    await page.locator(`ion-popover [data-testid=combo-menus-row-${menuId}-edit]`).click();
  }
  const form = page.locator('ion-modal[data-testid=combo-menu-form]');
  await expect(form).toBeVisible();
  return form;
}

async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/combo/menus' });
  for (const [code, name, price] of [
    ['HAK', 'Hake', 1400],
    ['CHI', 'Chicken', 1200],
  ] as const) {
    await call(owner.context, 'POST', '/inventory/products', { name: `${TAG} ${name} ${STAMP}`, sku: sku(code), price, tax_category_key: 'restaurant.food' }, 201);
  }
  menuId = (await call<{ id: string }>(owner.context, 'POST', '/combo/combos', { name: MENU, price: 1350, tax_category_key: 'restaurant.food' }, 201)).id;
  await call(owner.context, 'POST', '/combo/groups', { combo: MENU, name: 'Mains' }, 201);
  hakeChoice = (await call<{ id: string }>(owner.context, 'POST', '/combo/options', { combo: MENU, group: 'Mains', product: sku('HAK'), price_delta: 200 }, 201)).id;
  await call(owner.context, 'POST', '/combo/options', { combo: MENU, group: 'Mains', product: sku('CHI') }, 201);
  await owner.context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: combo-business-currency a business in Poland reads and types the closed price and the supplements of a menu in złoty in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'PL');
  const row = await menuRow(page);
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(row, `Menus at ${size.name}`).toContainText(zloty('13[.,]50'));
    await expect(row, `Menus at ${size.name}`).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, `Menus ${size.name}`);
    await page.screenshot({ path: shot(`${KEY}-list-${size.name}`) });
  }

  // The builder: the closed price and the hake's supplement, in złoty.
  await page.goto(`${A}/combo/menus/${menuId}`);
  const price = shown(page).locator('[data-testid=combo-builder-price]');
  const hake = shown(page).locator(`[data-testid=combo-choice-${hakeChoice}]`);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(price, `builder at ${size.name}`).toHaveText(zloty('13[.,]50'));
    await expect(hake, `builder at ${size.name}`).toContainText(zloty('2[.,]00', '+'));
    await expect(shown(page).locator('[data-testid=combo-builder-courses]'), `builder at ${size.name}`).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, `builder ${size.name}`);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
  }

  // Editing the hake: the field names the business's currency, shows złoty with its two decimals and reads «2,50 zł».
  await page.setViewportSize({ width: 1440, height: 900 });
  await shown(page).locator(`[data-testid=combo-choice-${hakeChoice}-edit]`).click();
  const course = shown(page).locator('[data-testid^=combo-course-][data-testid$=-delta]').first();
  await expect(course).toContainText('Supplement (PLN)');
  const delta = course.locator('input').first();
  await expect(delta).toHaveValue('2.00');
  await delta.fill('2,50 zł');
  await delta.blur();
  await expect(delta).toHaveValue('2.50');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-supplement-1440`) });
  await shown(page).locator('[data-testid^=combo-course-][data-testid$=-save]').first().click();
  await expect(hake).toContainText(zloty('2[.,]50', '+'));
  expect((await detail(context)).groups[0].options.find((o) => o.id === hakeChoice)?.price_delta).toBe(250);

  // «Edit details»: «Closed price (PLN)», «14,50» is 1450 grosze.
  await menuRow(page);
  const form = await editDetails(page);
  const field = form.locator('[data-testid=combo-menu-form-price]');
  await expect(field).toContainText('Closed price (PLN)');
  await expect(field).not.toContainText('€');
  const input = field.locator('input').first();
  await expect(input).toHaveValue('13.50');
  await input.fill('14,50');
  await input.blur();
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-form-1440`) });
  await form.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(form).toBeHidden();
  expect((await detail(context)).price).toBe(1450);
  await expect(shown(page).locator(`[data-testid=combo-menus-row][data-id="${menuId}"]`)).toContainText(zloty('14[.,]50'));
});

test(`${KEY}: combo-business-currency back in Spain the closed price and the supplements of a menu are in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  const row = await menuRow(page);
  await expect(row).toContainText(euros('14[.,]50'));
  await expect(row).not.toContainText('zł');
  await page.goto(`${A}/combo/menus/${menuId}`);
  await expect(shown(page).locator('[data-testid=combo-builder-price]')).toHaveText(euros('14[.,]50'));
  await expect(shown(page).locator(`[data-testid=combo-choice-${hakeChoice}]`)).toContainText(euros('2[.,]50', '+'));
  await expect(shown(page).locator('[data-testid=combo-builder-courses]')).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
  await menuRow(page);
  const form = await editDetails(page);
  await expect(form.locator('[data-testid=combo-menu-form-price]')).toContainText('Closed price (EUR)');
});
