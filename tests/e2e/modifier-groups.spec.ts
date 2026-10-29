// flow: MODIFIER-F01, MODIFIER-F02, MODIFIER-F03, MODIFIER-F04, MODIFIER-F05 — Modifiers in Chrome
// (apps/modifier/WORKBOOK.md) on hub `a` with the real Inventory and Taxes apps (no doubles), one test per flow:
// the owner finds the groups by their rule (F01; the employee reads them and their sheet with nothing that changes
// them), creates one from «New group» (F02; a taken name is refused under Name), edits it (F03; a maximum below its
// defaults is refused under Maximum) and deletes it after a confirmation that says what goes with it, adds, edits and
// deletes the options of its sheet (F04: a supplement, a discount with the ± key, a soft drink with its own tax
// category), and applies it to a product found by its SKU and to a category, then stops applying it (F05). Each screen
// in 390×844, 834×1112 and 1440×900 (`APP-MODIFIER-MODIFIER-Fnn-<w>`). Its data are named `E2E Mod …` / `E2E-MOD-…`
// and `afterAll` deletes exactly them.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, EMPLOYEE, horizontalOverflow, hostPage, login, painted, psql, shown, untilStill } from './helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const SKU = `E2E-MOD-${STAMP}`;
const PRODUCT = `E2E Burger ${STAMP}`;
const CATEGORY = `E2E Mod ${STAMP}`;
/** Every group of this spec is named `E2E Mod <what> <STAMP>`. */
const named = (what: string) => `E2E Mod ${what} ${STAMP}`;

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E Mod %'";
const OWN_PRODUCTS = "select id from inventory_product where sku like 'E2E-MOD-%'";
const OWN_CATEGORIES = "select id from inventory_category where name like 'E2E Mod %'";

function cleanUp(): void {
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS}) or product_id in (${OWN_PRODUCTS}) or category_id in (${OWN_CATEGORIES})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      "delete from modifier_modifiergroup where name like 'E2E Mod %'",
      `delete from inventory_stockmovement where product_id in (${OWN_PRODUCTS})`,
      `delete from inventory_productcategory where product_id in (${OWN_PRODUCTS}) or category_id in (${OWN_CATEGORIES})`,
      "delete from inventory_product where sku like 'E2E-MOD-%'",
      "delete from inventory_category where name like 'E2E Mod %'",
    ].join('; '),
  );
}

interface Group {
  id: string;
  name: string;
}

let productId: string;
let categoryId: string;

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/modifier/groups' });
  // The real Inventory: a product sold at 10 % (restaurant food) and a category of its own.
  const product = await api<{ id: string }>(owner.context, A, 'POST', '/inventory/products', {
    name: PRODUCT,
    sku: SKU,
    price: 800,
    tax_category_key: 'restaurant.food',
  });
  expect(product.status).toBe(201);
  productId = product.data.id;
  const category = await api<{ id: string }>(owner.context, A, 'POST', '/inventory/categories', { name: CATEGORY });
  expect(category.status).toBe(201);
  categoryId = category.data.id;
  await owner.context.close();
});

test.afterAll(cleanUp);

const tableReady = (page: Page) =>
  shown(page).locator('[data-testid=modifier-groups-row], [data-testid=modifier-groups-empty]').first().waitFor({ state: 'visible' });
const groupRow = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=modifier-groups-row][data-id="${id}"]`);
const dialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]`);
const sheet = (page: Page): Locator => dialog(page, 'modifier-sheet');

/** Types into an Ionic field of `scope`. */
async function fill(scope: Locator, testid: string, value: string): Promise<void> {
  const input = scope.locator(`[data-testid=${testid}] input`).first();
  await input.fill(value);
  await input.blur();
}

/** Picks the option `id` of a Combo after typing `text` in it (a click first opens its list, as the
 *  other specs do: typing alone into a dialog that is still presenting may leave the list unshown). */
async function pickCombo(page: Page, scope: Locator, testid: string, text: string, id: string): Promise<void> {
  const input = scope.locator(`[data-testid=${testid}] input`).first();
  await input.click();
  await input.fill(text);
  await page.locator(`[data-testid="${testid}-option-${id}"]`).click();
}

/** Runs a row action of the groups table: its inline button, or the row's «⋮» menu when it folded there. */
async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `modifier-groups-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=modifier-groups-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

/** A group made through the API, with its options (setup, never the check). */
async function makeGroup(context: BrowserContext, fields: Record<string, unknown>, options: Record<string, unknown>[] = []): Promise<Group> {
  const made = await api<Group>(context, A, 'POST', '/modifier/groups', fields);
  expect(made.status, `group ${JSON.stringify(fields)}`).toBe(201);
  for (const option of options) {
    const res = await api(context, A, 'POST', '/modifier/options', { group_id: made.data.id, ...option });
    expect(res.status, `option ${JSON.stringify(option)}`).toBe(201);
  }
  return made.data;
}

async function groupByName(context: BrowserContext, name: string): Promise<Group> {
  const res = await api<Group>(context, A, 'GET', `/modifier/groups/detail?group=${encodeURIComponent(name)}`);
  expect(res.status, `group ${name}`).toBe(200);
  return res.data;
}

/** The screen in the three viewports, once `ready` says it painted; never a horizontal scroll. */
async function shoot(page: Page, key: string, ready: () => Promise<void> = async () => {}): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    // The page laid out at its new size, then nothing moving: Ionic's sheets and notices animate in their shadow roots.
    await painted(page);
    await untilStill(page);
    await expect
      .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${size.label}` })
      .toBeLessThanOrEqual(0);
    await capture(page, `APP-MODIFIER-${key}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function openGroups(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/modifier/groups');
  await tableReady(page);
  await shown(page).locator('[data-testid=modifier-groups-search] input').fill(STAMP);
}

test('MODIFIER-F01: the groups are found by name and say their rule, their options and where they apply', async ({ page, context }) => {
  await login(page, A, '/modifier/groups');
  const doneness = await makeGroup(context, { name: named('Doneness'), kitchen_name: 'POINT', min_choices: 1, max_choices: 1, sort_order: 1 }, [
    { name: 'Rare' },
    { name: 'Well done' },
  ]);
  const sauces = await makeGroup(context, { name: named('Sauces'), max_choices: 3, allow_repeat: true, sort_order: 2 }, [{ name: 'Mayo' }]);
  expect((await api(context, A, 'POST', '/modifier/links/attach', { group_id: doneness.id, product_id: productId })).status).toBe(201);
  expect((await api(context, A, 'POST', '/modifier/links/attach', { group_id: doneness.id, category_id: categoryId })).status).toBe(201);

  await openGroups(page);
  const rows = shown(page).locator('[data-testid=modifier-groups-row]');
  await expect(rows).toHaveCount(2);
  // By their order: Doneness first; the kitchen column says its kitchen name, or the name when it has none.
  await expect(rows.nth(0)).toHaveAttribute('data-id', doneness.id);
  await expect(groupRow(page, doneness.id)).toContainText('POINT');
  await expect(groupRow(page, doneness.id)).toContainText('Required (min. 1) · max. 1');
  await expect(groupRow(page, sauces.id)).toContainText('Optional · max. 3 · repeats');
  // How many options each one has and on how many products and categories it is asked.
  const cells = (id: string) => groupRow(page, id).locator('[role=cell]');
  await expect(cells(doneness.id).nth(3)).toHaveText('2');
  await expect(cells(doneness.id).nth(4)).toHaveText('2');
  await expect(cells(sauces.id).nth(4)).toHaveText('0');
  await shoot(page, 'MODIFIER-F01', () => expect(groupRow(page, sauces.id)).toBeVisible());

  // A search that finds nothing says so, never «No modifier groups yet.».
  await shown(page).locator('[data-testid=modifier-groups-search] input').fill(`${STAMP}-none`);
  await expect(shown(page).locator('[data-testid=modifier-groups-empty]')).toContainText('No results');
});

test('MODIFIER-F01: the employee reads the groups and their sheet, with nothing that changes them', async ({ browser }) => {
  // Made by the owner, through the API (setup, never the check).
  const owner = await hostPage(browser, A, { next: '/modifier/groups' });
  const made = await makeGroup(owner.context, { name: named('Cooking'), min_choices: 1, max_choices: 1 }, [{ name: 'Rare' }]);
  const employee = await hostPage(browser, A, { next: '/modifier/groups', credentials: EMPLOYEE });
  const { page } = employee;
  try {
    // Positive control: the owner has what the employee must not.
    await tableReady(owner.page);
    await expect(shown(owner.page).locator('[data-testid=modifier-groups-add]')).toBeVisible();

    await tableReady(page);
    await shown(page).locator('[data-testid=modifier-groups-search] input').fill(STAMP);
    await expect(groupRow(page, made.id)).toBeVisible();
    await expect(shown(page).locator('[data-testid=modifier-groups-add]')).toHaveCount(0);
    await expect(shown(page).locator(`[data-testid=modifier-groups-row-${made.id}-delete]`)).toHaveCount(0);
    await groupRow(page, made.id).locator('[role=cell]').first().click();
    await expect(sheet(page)).toBeVisible();
    await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-row-]')).toContainText('Rare');
    for (const hook of ['modifier-sheet-options-add', 'modifier-sheet-links-add']) {
      await expect(sheet(page).locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
    }
    await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-delete-]')).toHaveCount(0);
    // The API refuses the write too.
    const refused = await api<{ error: { code: string } }>(employee.context, A, 'POST', '/modifier/groups', { name: named('Nope') });
    expect([refused.status, refused.data.error.code]).toEqual([403, 'permission_denied']);
    await shoot(page, 'MODIFIER-F01-employee', () => expect(sheet(page).locator('[data-testid=modifier-sheet-title]')).toBeVisible());
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});

test('MODIFIER-F02: «New group» creates it with its rule; a taken name is refused under Name', async ({ page, context }) => {
  await openGroups(page);
  await shown(page).locator('[data-testid=modifier-groups-add]').click();
  const form = dialog(page, 'modifier-group-form');
  await expect(form).toBeVisible();
  await fill(form, 'modifier-group-form-name', named('Sauces new'));
  await fill(form, 'modifier-group-form-kitchen_name', 'SAUCE');
  await fill(form, 'modifier-group-form-min_choices', '1');
  await fill(form, 'modifier-group-form-max_choices', '2');
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form).toBeHidden();
  const group = await groupByName(context, named('Sauces new'));
  // It arrives live, with its rule.
  await expect(groupRow(page, group.id)).toContainText('Required (min. 1) · max. 2');
  await expect(groupRow(page, group.id)).toContainText('SAUCE');

  // A taken name (whatever the case) is refused under Name; what was typed stays.
  await shown(page).locator('[data-testid=modifier-groups-add]').click();
  await expect(form).toBeVisible();
  await fill(form, 'modifier-group-form-name', named('Sauces new').toLowerCase());
  await fill(form, 'modifier-group-form-max_choices', '4');
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form.locator('[data-testid=modifier-group-form-name]')).toHaveClass(/ion-invalid/);
  await expect(form).toContainText('There is already a group with that name.');
  await expect(form.locator('[data-testid=modifier-group-form-max_choices] input')).toHaveValue('4');
  await shoot(page, 'MODIFIER-F02', () => expect(form).toContainText('There is already a group with that name.'));
  await form.locator('[data-testid=modifier-group-form-cancel]').click();
  await expect(form).toBeHidden();
});

test('MODIFIER-F03: Edit changes only what is touched, a maximum below the defaults is refused, Delete says what goes', async ({ page, context }) => {
  await login(page, A, '/modifier/groups');
  const group = await makeGroup(context, { name: named('Extras'), kitchen_name: 'EXTRA', max_choices: 3 }, [
    { name: 'Cheese', is_default: true },
    { name: 'Bacon', is_default: true },
  ]);
  expect((await api(context, A, 'POST', '/modifier/links/attach', { group_id: group.id, product_id: productId })).status).toBe(201);
  await openGroups(page);
  await expect(groupRow(page, group.id)).toContainText('Optional · max. 3');

  await rowAction(page, group.id, 'edit');
  const form = dialog(page, 'modifier-group-form');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=modifier-group-form-name] input')).toHaveValue(named('Extras'));
  // Two options come chosen by default: a maximum of one cannot hold them.
  await fill(form, 'modifier-group-form-max_choices', '1');
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form.locator('[data-testid=modifier-group-form-max_choices]')).toHaveClass(/ion-invalid/);
  await expect(form).toContainText('This group has more options chosen by default than its maximum.');
  await shoot(page, 'MODIFIER-F03', () => expect(form).toContainText('more options chosen by default'));
  await fill(form, 'modifier-group-form-max_choices', '2');
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(groupRow(page, group.id)).toContainText('Optional · max. 2');
  // What was not touched stays: its kitchen name.
  await expect(groupRow(page, group.id)).toContainText('EXTRA');

  // Deleting it, after a confirmation that says its options and where it applies go with it.
  await rowAction(page, group.id, 'delete');
  const confirm = dialog(page, 'modifier-groups-delete');
  await expect(confirm).toContainText('2 option(s) will be deleted with it.');
  await expect(confirm).toContainText('It will stop applying to 1 product(s) or category(ies).');
  await shoot(page, 'MODIFIER-F03-delete', () => expect(confirm).toBeVisible());
  await confirm.locator('[data-testid=modifier-groups-delete-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(groupRow(page, group.id)).toHaveCount(0);
  expect((await api(context, A, 'GET', `/modifier/groups/detail?id=${group.id}`)).status).toBe(404);
});

test('MODIFIER-F04: the sheet adds, edits and deletes the options with their supplement and their own tax', async ({ page, context }) => {
  await login(page, A, '/modifier/groups');
  const group = await makeGroup(context, { name: named('Toppings'), max_choices: 2 });
  await openGroups(page);
  await groupRow(page, group.id).locator('[role=cell]').first().click();
  await expect(sheet(page)).toBeVisible();
  await expect(sheet(page).locator('[data-testid=modifier-sheet-title]')).toContainText(named('Toppings'));
  await expect(sheet(page).locator('[data-testid=modifier-sheet-options-empty]')).toBeVisible();
  const optionForm = dialog(page, 'modifier-option-form');
  const optionRows = sheet(page).locator('[data-testid^=modifier-sheet-options-row-]');

  // A supplement, chosen by default.
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  await expect(optionForm).toBeVisible();
  await fill(optionForm, 'modifier-option-form-name', 'Mayo');
  await fill(optionForm, 'modifier-option-form-kitchen_name', '+MAYO');
  await fill(optionForm, 'modifier-option-form-price_delta', '0.30');
  await optionForm.locator('[data-testid=modifier-option-form-is_default]').click();
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  // A discount: the phone's decimal keypad has no minus, the ± key gives it.
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  await expect(optionForm).toBeVisible();
  await fill(optionForm, 'modifier-option-form-name', 'No sauce');
  await fill(optionForm, 'modifier-option-form-price_delta', '0.50');
  await optionForm.locator('[data-testid=modifier-option-form-price_delta-sign]').click();
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  // A soft drink at 21 %: its own tax category.
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  await expect(optionForm).toBeVisible();
  await fill(optionForm, 'modifier-option-form-name', 'Soda');
  await fill(optionForm, 'modifier-option-form-price_delta', '2.50');
  await pickCombo(page, optionForm, 'modifier-option-form-tax_category_key', 'generic', 'product.generic');
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  await expect(optionRows).toHaveCount(3);
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText(/\+€?0[.,]30/);
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText('By default');
  // With its sign, as `lib/format.ts` paints a discount («-€0.50»).
  await expect(optionRows.filter({ hasText: 'No sauce' })).toContainText(/-€?0[.,]50/);
  await expect(optionRows.filter({ hasText: 'Soda' })).toContainText('Own tax');
  const prices = await api<{ rows: { name: string; price_delta: number }[] }>(context, A, 'GET', `/modifier/options?group_id=${group.id}`);
  expect(prices.data.rows.map((row) => [row.name, row.price_delta]).sort()).toEqual([
    ['Mayo', 30],
    ['No sauce', -50],
    ['Soda', 250],
  ]);

  // Editing keeps what is not touched: only the supplement of the mayo changes.
  await optionRows.filter({ hasText: 'Mayo' }).locator('[data-testid^=modifier-sheet-options-edit-]').click();
  await expect(optionForm).toBeVisible();
  await expect(optionForm.locator('[data-testid=modifier-option-form-kitchen_name] input')).toHaveValue('+MAYO');
  await fill(optionForm, 'modifier-option-form-price_delta', '0.40');
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText(/\+€?0[.,]40/);
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText('By default');
  await shoot(page, 'MODIFIER-F04', () => expect(optionRows).toHaveCount(3));

  // Deleting one, after its confirmation.
  await optionRows.filter({ hasText: 'Soda' }).locator('[data-testid^=modifier-sheet-options-delete-]').click();
  await page.locator('[data-testid=modifier-sheet-option-delete-submit]').click();
  await expect(optionRows).toHaveCount(2);
  await expect(optionRows.filter({ hasText: 'Soda' })).toHaveCount(0);
});

test('MODIFIER-F05: the group is applied to a product by its SKU and to a category, and stops applying', async ({ page, context }) => {
  await login(page, A, '/modifier/groups');
  const group = await makeGroup(context, { name: named('Sides') }, [{ name: 'Fries' }]);
  await openGroups(page);
  await groupRow(page, group.id).locator('[role=cell]').first().click();
  await expect(sheet(page)).toBeVisible();
  await expect(sheet(page).locator('[data-testid=modifier-sheet-links-empty]')).toBeVisible();
  const linkForm = dialog(page, 'modifier-link-form');
  const linkRows = sheet(page).locator('[data-testid^=modifier-sheet-links-row-]');

  // A product, found by its SKU.
  await sheet(page).locator('[data-testid=modifier-sheet-links-add]').click();
  await expect(linkForm).toBeVisible();
  await pickCombo(page, linkForm, 'modifier-link-form-target', SKU, productId);
  await linkForm.locator('[data-testid=modifier-link-form-submit]').click();
  await expect(linkForm).toBeHidden();
  // A category, found by its name.
  await sheet(page).locator('[data-testid=modifier-sheet-links-add]').click();
  await expect(linkForm).toBeVisible();
  await linkForm.locator('[data-testid=modifier-link-form-kind-category]').click();
  await pickCombo(page, linkForm, 'modifier-link-form-target', CATEGORY, categoryId);
  await linkForm.locator('[data-testid=modifier-link-form-submit]').click();
  await expect(linkForm).toBeHidden();
  await expect(linkRows).toHaveCount(2);
  await expect(linkRows.filter({ hasText: SKU })).toContainText(`Product · ${PRODUCT} (${SKU})`);
  await expect(linkRows.filter({ hasText: `Category · ${CATEGORY}` })).toHaveCount(1);
  await shoot(page, 'MODIFIER-F05', () => expect(linkRows).toHaveCount(2));

  // The same product twice is refused inside the form.
  await sheet(page).locator('[data-testid=modifier-sheet-links-add]').click();
  await expect(linkForm).toBeVisible();
  await pickCombo(page, linkForm, 'modifier-link-form-target', SKU, productId);
  await linkForm.locator('[data-testid=modifier-link-form-submit]').click();
  await expect(linkForm).toContainText('This group already applies there.');
  await linkForm.locator('[data-testid=modifier-link-form-cancel]').click();
  await expect(linkForm).toBeHidden();

  // It stops applying to the product, after its confirmation: the category stays.
  await linkRows.filter({ hasText: SKU }).locator('[data-testid^=modifier-sheet-links-detach-]').click();
  await page.locator('[data-testid=modifier-sheet-link-detach-submit]').click();
  await expect(linkRows).toHaveCount(1);
  await expect(linkRows.first()).toContainText(`Category · ${CATEGORY}`);
  const asked = await api<{ groups: { name: string }[] }>(context, A, 'GET', `/modifier/groups/for_target?product=${SKU}`);
  expect(asked.data.groups.map((g) => g.name)).not.toContain(named('Sides'));
});
