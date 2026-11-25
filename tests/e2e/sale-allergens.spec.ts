import { expect, type BrowserContext, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp, tillReady } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-ALG-${RUN}`;
const MENU = `e2e Allergen Menu ${RUN}`;
const GROUP = `E2E Allergen Group ${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

const products: Record<string, Product> = {};
const options: Record<string, string> = {};
let menuId = '';

async function post<T>(context: BrowserContext, path: string, body: unknown): Promise<T> {
  const response = await api<T>(context, A, 'POST', path, body);
  expect(response.status, `${path}: ${JSON.stringify(response.data)}`).toBe(201);
  return response.data;
}

function cleanRun(): void {
  const combos = "select id from combo_combo where name like 'e2e Allergen %'";
  const groups = "select id from modifier_modifiergroup where name like 'E2E Allergen %'";
  psql(
    [
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where id in (${combos})`,
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      `delete from modifier_modifiergroup where id in (${groups})`,
    ].join('; '),
  );
}

async function snap(page: Page, name: string, prepare?: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await prepare?.();
    await untilStill(page);
    expect(await horizontalOverflow(page), `${name} at ${size.label}`).toBeLessThanOrEqual(0);
    await capture(page, `sale-allergens-${name}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await openTillCart(page);
}

async function snapLine(page: Page, name: string, focus: ReturnType<typeof lineOf>): Promise<void> {
  return snap(page, name, async () => {
    await openTillCart(page);
    await focus.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  });
}

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();

test.afterAll(() => {
  cleanSales();
  cleanRun();
  cleanInventory();
  restoreDrawer();
});

test('the waiter sees dish allergens and the customer allergy on lines and sheets', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const context = page.context();
  cleanRun();
  await drawerOff(context);
  for (const [key, name, allergens] of [
    ['plate', 'Allergen plate', ['gluten', 'milk']],
    ['allergy', 'Allergy plate', ['gluten']],
    ['plain', 'Plain plate', []],
    ['flan', 'Flan', ['egg', 'milk']],
  ] as const) {
    products[key] = await createProduct(context, { name: `E2E ${name} ${RUN}`, sku: `${SKU}-${key}`, price: 800, tax_category_key: FOOD, allergens });
  }
  const group = await post<{ id: string }>(context, '/modifier/groups', { name: GROUP, max_choices: 1 });
  const cheese = await post<{ id: string }>(context, '/modifier/options', { group_id: group.id, name: 'Cheese', price_delta: 0, allergens: ['milk'] });
  const extra = await post<{ id: string }>(context, '/modifier/options', { group_id: group.id, name: 'Extra', price_delta: 0 });
  await post(context, '/modifier/links/attach', { group_id: group.id, product_id: products.plate.id });
  menuId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, price: 1400, tax_category_key: FOOD })).id;
  for (const course of ['Main', 'Dessert']) await post(context, '/combo/groups', { combo: MENU, name: course, min_choices: 1, max_choices: 1 });
  for (const [key, course] of [['plate', 'Main'], ['flan', 'Dessert']] as const) {
    options[key] = (await post<{ id: string }>(context, '/combo/options', { combo: MENU, group: course, product: products[key].sku })).id;
  }
  await tillReady(page);

  await shown(page).locator(`[data-testid=pos-product-${products.plate.id}]`).click();
  const modifiers = page.locator('[data-testid=pos-options]');
  await expect(modifiers).toBeVisible();
  await expect(modifiers.locator('[data-testid=pos-options-allergens]')).toHaveText('Allergens: Gluten, Milk');
  await expect(modifiers.locator(`[data-testid=pos-option-allergens-${cheese.id}]`)).toHaveText('Allergens: Milk');
  await expect(modifiers.locator(`[data-testid=pos-option-allergens-${extra.id}]`)).toHaveCount(0);
  const tileHeight = async (id: string) => (await modifiers.locator(`[data-testid=pos-option-${id}]`).boundingBox())?.height;
  expect(await tileHeight(extra.id), 'a choice without allergens stands as tall as the one beside it that says them').toBe(await tileHeight(cheese.id));
  await snap(page, 'modifiers');
  await modifiers.locator('[data-testid=pos-options-add]').click();
  await expect(modifiers).toBeHidden();
  await snapLine(page, 'allergen-line', lineOf(page, products.plate.name));

  await shown(page).locator(`[data-testid=pos-product-${products.allergy.id}]`).click();
  const allergyLine = lineOf(page, products.allergy.name);
  await allergyLine.locator('[data-testid$=-note]').click();
  const note = page.locator('[data-testid=pos-note]');
  await expect(note.locator('[data-testid=pos-note-allergy]')).toContainText('Customer allergy');
  await note.locator('[data-testid=pos-note-allergy-gluten] ion-checkbox').click();
  await snap(page, 'note');
  await note.locator('[data-testid=pos-note-save]').click();
  await expect(note).toBeHidden();
  await expect(allergyLine.locator('[data-testid$=-allergy]')).toContainText('Allergy: Gluten');
  await expect(allergyLine.locator('[data-testid$=-allergy-match]')).toHaveText('The dish contains Gluten');
  await snapLine(page, 'allergy-line', allergyLine);

  await shown(page).locator(`[data-testid=pos-product-${products.plain.id}]`).click();
  const plainLine = lineOf(page, products.plain.name);
  await expect(plainLine).toBeVisible();
  await expect(plainLine.locator('[data-testid$=-allergens]')).toHaveCount(0);
  await expect(plainLine.locator('[data-testid$=-allergy]')).toHaveCount(0);
  await snapLine(page, 'plain-line', plainLine);

  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).click();
  const menu = page.locator('[data-testid=pos-menu]');
  await expect(menu.locator(`[data-testid=pos-menu-dish-allergens-${options.plate}]`)).toHaveText('Allergens: Gluten, Milk');
  await expect(menu.locator(`[data-testid=pos-menu-dish-allergens-${options.flan}]`)).toHaveText('Allergens: Egg, Milk');
  await snap(page, 'menu');
  await menu.locator(`[data-testid=pos-menu-dish-${options.plate}]`).click();
  await menu.locator(`[data-testid=pos-menu-dish-${options.flan}]`).click();
  await menu.locator('[data-testid=pos-menu-add]').click();
  await expect(menu).toBeHidden();
  const menuLine = lineOf(page, MENU);
  await expect(menuLine.locator('[data-testid*=-dish-allergens-]').filter({ hasText: 'Allergen plate' })).toContainText('Allergens: Gluten, Milk');
  await expect(menuLine.locator('[data-testid*=-dish-allergens-]').filter({ hasText: 'Flan' })).toContainText('Allergens: Egg, Milk');
  await snapLine(page, 'menu-line', menuLine.locator('[data-testid*=-dish-allergens-]').filter({ hasText: 'Flan' }));
  await snap(page, 'lines', () => openTillCart(page));
});
