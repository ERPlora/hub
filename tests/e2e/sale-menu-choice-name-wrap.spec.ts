// flow: SALE-F12, SALE-F11 — the name of a choice in the till's menu sheet, in English, beside its supplement: a menu
// whose «Dessert» offers «Home-made flan» and «Cheesecake» for 1.00 more. In every size the name wraps only between
// words, and when a word does not fit beside the supplement the supplement moves under the name, still inside its
// choice. Only a word longer than the whole choice («Schwarzwälderkirschtorte») is split, and it stays inside it.
// Measured letter by letter in Chrome with the sheet's own stylesheet, at 1280×720, 1440×900, 820×1180 and 375×667.
// What a run makes — products `E2E-SMW-<run>-…` and its menu «e2e Wrap Menu …» — goes.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-SMW-${RUN}`;
const MENU = `e2e Wrap Menu ${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '1280', width: 1280, height: 720 },
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
];

interface ForSale {
  rows: { id: string; groups: { options: { id: string; product_id: string }[] }[] }[];
}

let menuId = '';
let flan: Product;
let cheesecake: Product;
let blackForest: Product;

function cleanRun(): void {
  const combos = "select id from combo_combo where name like 'e2e Wrap Menu %'";
  psql(
    [
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where id in (${combos})`,
    ].join('; '),
  );
}

async function post<T>(context: BrowserContext, path: string, body: unknown): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(201);
  return res.data;
}

/** Every place where the text of `name` jumps to the next line between two letters of one word («Cheesecak|e»). A
 *  line may still end at a space or after a hyphen («Home-|made»). */
async function wordsBroken(name: Locator): Promise<string[]> {
  return name.evaluate((element) => {
    const text = element.firstChild;
    if (!text || text.nodeType !== Node.TEXT_NODE) return ['the name is not one text'];
    const value = text.textContent ?? '';
    const range = document.createRange();
    const tops = [...value].map((_, i) => {
      range.setStart(text, i);
      range.setEnd(text, i + 1);
      return Math.round(range.getClientRects()[0]?.top ?? Number.NaN);
    });
    return tops.flatMap((top, i) => {
      if (i === 0 || !(top > tops[i - 1]) || /\s/.test(value[i]) || /[\s-]/.test(value[i - 1])) return [];
      return [`${value.slice(0, i)}|${value.slice(i)}`];
    });
  });
}

/** How far the name or the supplement of a choice sticks out of it, in pixels (0: both inside). */
async function stickingOut(choice: Locator): Promise<number> {
  return choice.evaluate((button) => {
    const outer = button.getBoundingClientRect();
    const parts = [...button.querySelectorAll('.pos-options__label > span:first-child, .pos-options__delta')];
    if (parts.length !== 2) return Number.NaN;
    return Math.max(
      ...parts.map((part) => {
        const inner = part.getBoundingClientRect();
        return Math.max(0, outer.left - inner.left, inner.right - outer.right, outer.top - inner.top, inner.bottom - outer.bottom);
      }),
    );
  });
}

test.beforeAll(async ({ browser }) => {
  cleanRun();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  flan = await createProduct(context, { name: 'Home-made flan', sku: `${SKU}-FLA`, price: 450, tax_category_key: FOOD, allergens: ['egg', 'milk'] });
  cheesecake = await createProduct(context, { name: 'Cheesecake', sku: `${SKU}-CHE`, price: 550, tax_category_key: FOOD, allergens: ['milk', 'egg', 'gluten'] });
  blackForest = await createProduct(context, { name: 'Schwarzwälderkirschtorte', sku: `${SKU}-BFC`, price: 650, tax_category_key: FOOD });
  menuId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, kitchen_name: 'MENU', price: 1350, tax_category_key: FOOD })).id;
  await post(context, '/combo/groups', { combo: MENU, name: 'Dessert' });
  await post(context, '/combo/options', { combo: MENU, group: 'Dessert', product: flan.sku });
  await post(context, '/combo/options', { combo: MENU, group: 'Dessert', product: cheesecake.sku, price_delta: 100 });
  await post(context, '/combo/options', { combo: MENU, group: 'Dessert', product: blackForest.sku, price_delta: 200 });
  await context.close();
});

test.afterAll(() => {
  cleanRun();
  cleanInventory();
  restoreDrawer();
});

async function openMenu(page: Page): Promise<Locator> {
  await page.setViewportSize({ width: 1280, height: 720 });
  await login(page, A, '/sale/pos');
  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await expect(sheet).toBeVisible();
  return sheet;
}

test('SALE-F12: a choice with a supplement keeps every word of its name whole, in every size', async ({ page, context }) => {
  const sheet = await openMenu(page);
  const res = await api<ForSale>(context, A, 'GET', '/combo/combos/for_sale?limit=50');
  const offer = res.data.rows.find((row) => row.id === menuId)!.groups.flatMap((group) => group.options);
  const optionOf = (product: Product) => offer.find((option) => option.product_id === product.id)!.id;
  const choice = sheet.locator(`[data-testid=pos-menu-dish-${optionOf(cheesecake)}]`);
  const name = sheet.locator(`[data-testid=pos-menu-dish-name-${optionOf(cheesecake)}]`);
  await expect(name).toHaveText('Cheesecake');
  await expect(choice).toContainText('+€1.00');
  const longWord = sheet.locator(`[data-testid=pos-menu-dish-${optionOf(blackForest)}]`);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await choice.scrollIntoViewIfNeeded();
    await expect.poll(() => wordsBroken(name), { message: `«Cheesecake» split inside the word at ${size.label}` }).toEqual([]);
    await expect.poll(() => wordsBroken(sheet.locator(`[data-testid=pos-menu-dish-name-${optionOf(flan)}]`))).toEqual([]);
    await expect.poll(() => stickingOut(choice), { message: `the name or the supplement out of its choice at ${size.label}` }).toBe(0);
    await expect.poll(() => stickingOut(longWord), { message: `a word longer than its choice sticks out at ${size.label}` }).toBe(0);
    await expect.poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${size.label}` }).toBeLessThanOrEqual(0);
    await capture(page, `SALE-F12-choice-name-wrap-${size.label}`);
  }
});
