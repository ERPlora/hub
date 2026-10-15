// Modifiers in Chrome (apps/modifier/WORKBOOK.md, MODIFIER-F01 to F07), on hub `a` with the real Inventory
// and Taxes apps (no doubles): the owner creates a group from «New group» (a taken name is refused under
// Name), opens its sheet, adds a supplement and a soft drink with its own tax category, applies the
// group to a product found by its SKU, and the till's reads (`modifier.group.for_target`,
// `modifier.selection.resolve`) answer with them; then stops applying it, deletes an option and the
// group. The employee reads the table and the sheet without any button that changes them. Screenshots
// in the three viewports. Its data are named `E2E …` / `E2E-MOD-…` and `afterAll` deletes exactly them.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, login, psql, shot, shown } from './helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const GROUP = `E2E Sauces ${STAMP}`;
const SKU = `E2E-MOD-${STAMP}`;
const PRODUCT = `E2E Burger ${STAMP}`;
const CATEGORY = `E2E Mod ${STAMP}`;

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E %'";
const OWN_PRODUCTS = "select id from inventory_product where sku like 'E2E-MOD-%'";
const OWN_CATEGORIES = "select id from inventory_category where name like 'E2E Mod %'";

test.afterAll(() => {
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS}) or product_id in (${OWN_PRODUCTS}) or category_id in (${OWN_CATEGORIES})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      "delete from modifier_modifiergroup where name like 'E2E %'",
      `delete from inventory_stockmovement where product_id in (${OWN_PRODUCTS})`,
      `delete from inventory_productcategory where product_id in (${OWN_PRODUCTS}) or category_id in (${OWN_CATEGORIES})`,
      "delete from inventory_product where sku like 'E2E-MOD-%'",
      "delete from inventory_category where name like 'E2E Mod %'",
    ].join('; '),
  );
});

interface Group {
  id: string;
  name: string;
}

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

async function groupByName(context: BrowserContext, name: string): Promise<Group> {
  const res = await api<Group>(context, A, 'GET', `/modifier/groups/detail?group=${encodeURIComponent(name)}`);
  expect(res.status, `group ${name}`).toBe(200);
  return res.data;
}

async function shoot(page: Page, name: string): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${viewport.label}` })
      .toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('MODIFIER-F01 to F07: the owner builds a group, applies it to a product and the till values the choice', async ({ page, context }) => {
  await login(page, A, '/modifier/groups');
  await tableReady(page);

  // The real Inventory: a product sold at 10 % (restaurant food) in a category of its own.
  const product = await api<{ id: string }>(context, A, 'POST', '/inventory/products', {
    name: PRODUCT,
    sku: SKU,
    price: 800,
    tax_category_key: 'restaurant.food',
  });
  expect(product.status).toBe(201);
  expect((await api(context, A, 'POST', '/inventory/categories', { name: CATEGORY })).status).toBe(201);

  // MODIFIER-F02: «New group».
  await shown(page).locator('[data-testid=modifier-groups-add]').click();
  const form = dialog(page, 'modifier-group-form');
  await expect(form).toBeVisible();
  await fill(form, 'modifier-group-form-name', GROUP);
  await fill(form, 'modifier-group-form-kitchen_name', 'SAUCE');
  await fill(form, 'modifier-group-form-min_choices', '1');
  await fill(form, 'modifier-group-form-max_choices', '2');
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form).toBeHidden();
  const group = await groupByName(context, GROUP);
  // It arrives live, with its rule.
  await shown(page).locator('[data-testid=modifier-groups-search] input').fill(STAMP);
  await expect(groupRow(page, group.id)).toContainText(/Required \(min\. 1\) · max\. 2|Obligatorio \(mín\. 1\) · máx\. 2/);
  await expect(groupRow(page, group.id)).toContainText('SAUCE');

  // A taken name (whatever the case) is refused under Name; what was typed stays.
  await shown(page).locator('[data-testid=modifier-groups-add]').click();
  await expect(form).toBeVisible();
  await fill(form, 'modifier-group-form-name', GROUP.toLowerCase());
  await form.locator('[data-testid=modifier-group-form-submit]').click();
  await expect(form.locator('[data-testid=modifier-group-form-name]')).toHaveClass(/ion-invalid/);
  await expect(form).toContainText(/There is already a group with that name|Ya hay un grupo con ese nombre/);
  await form.locator('[data-testid=modifier-group-form-cancel]').click();
  await expect(form).toBeHidden();
  await shoot(page, 'modifier-groups');

  // MODIFIER-F04: the sheet, a supplement and a soft drink with its own tax category.
  await groupRow(page, group.id).locator('[role=cell]').first().click();
  await expect(sheet(page)).toBeVisible();
  await expect(sheet(page).locator('[data-testid=modifier-sheet-title]')).toContainText(GROUP);
  await expect(sheet(page).locator('[data-testid=modifier-sheet-options-empty]')).toBeVisible();
  const optionForm = dialog(page, 'modifier-option-form');
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  await expect(optionForm).toBeVisible();
  await fill(optionForm, 'modifier-option-form-name', 'Mayo');
  await fill(optionForm, 'modifier-option-form-kitchen_name', '+MAYO');
  await fill(optionForm, 'modifier-option-form-price_delta', '0.30');
  await optionForm.locator('[data-testid=modifier-option-form-is_default]').click();
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  await expect(optionForm).toBeVisible();
  await fill(optionForm, 'modifier-option-form-name', 'Soda');
  await fill(optionForm, 'modifier-option-form-price_delta', '2.50');
  await pickCombo(page, optionForm, 'modifier-option-form-tax_category_key', 'generic', 'product.generic');
  await optionForm.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(optionForm).toBeHidden();
  const optionRows = sheet(page).locator('[data-testid^=modifier-sheet-options-row-]');
  await expect(optionRows).toHaveCount(2);
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText(/\+€?0[.,]30/);
  await expect(optionRows.filter({ hasText: 'Mayo' })).toContainText(/By default|Por defecto/);
  await expect(optionRows.filter({ hasText: 'Soda' })).toContainText(/Own tax|IVA propio/);

  // MODIFIER-F05: applied to the product, found by its SKU.
  await expect(sheet(page).locator('[data-testid=modifier-sheet-links-empty]')).toBeVisible();
  await sheet(page).locator('[data-testid=modifier-sheet-links-add]').click();
  const linkForm = dialog(page, 'modifier-link-form');
  await expect(linkForm).toBeVisible();
  await pickCombo(page, linkForm, 'modifier-link-form-target', SKU, product.data.id);
  await linkForm.locator('[data-testid=modifier-link-form-submit]').click();
  await expect(linkForm).toBeHidden();
  const linkRows = sheet(page).locator('[data-testid^=modifier-sheet-links-row-]');
  await expect(linkRows).toHaveCount(1);
  await expect(linkRows.first()).toContainText(`${PRODUCT} (${SKU})`);
  await shoot(page, 'modifier-sheet');

  // MODIFIER-F06 and F07: what the till reads for that product, and the valuation of a choice.
  const target = await api<{ groups: Array<{ name: string; options: Array<{ id: string; name: string; is_default: boolean }> }> }>(
    context,
    A,
    'GET',
    `/modifier/groups/for_target?product=${SKU}`,
  );
  expect(target.status).toBe(200);
  const [asked] = target.data.groups.filter((g) => g.name === GROUP);
  expect(asked.options.map((o) => [o.name, o.is_default])).toEqual([
    ['Mayo', true],
    ['Soda', false],
  ]);
  const ids = Object.fromEntries(asked.options.map((o) => [o.name, o.id]));
  const valued = await api<{ folded_delta: number; kitchen_text: string; picks: Array<{ own_line: boolean }> }>(
    context,
    A,
    'GET',
    `/modifier/selections/resolve?product=${SKU}&option_ids=${ids.Mayo}&option_ids=${ids.Soda}`,
  );
  expect(valued.status).toBe(200);
  expect([valued.data.folded_delta, valued.data.kitchen_text, valued.data.picks.map((p) => p.own_line)]).toEqual([30, '+MAYO, Soda', [false, true]]);
  const missing = await api<{ error: { code: string } }>(context, A, 'GET', `/modifier/selections/resolve?product=${SKU}`);
  expect([missing.status, missing.data.error.code]).toEqual([409, 'modifier.choice_below_min']);

  // Stop applying it, and delete an option: each after its confirmation.
  await linkRows.first().locator('[data-testid^=modifier-sheet-links-detach-]').click();
  await page.locator('[data-testid=modifier-sheet-link-detach-submit]').click();
  await expect(sheet(page).locator('[data-testid=modifier-sheet-links-empty]')).toBeVisible();
  await optionRows.filter({ hasText: 'Soda' }).locator('[data-testid^=modifier-sheet-options-delete-]').click();
  await page.locator('[data-testid=modifier-sheet-option-delete-submit]').click();
  await expect(optionRows).toHaveCount(1);
  await sheet(page).locator('[data-testid=modifier-sheet-close]').click();
  await expect(sheet(page)).toBeHidden();

  // MODIFIER-F03: deleting the group, after its confirmation, takes it off the table.
  await rowAction(page, group.id, 'delete');
  const confirm = dialog(page, 'modifier-groups-delete');
  await expect(confirm).toContainText(/1 option\(s\) will be deleted|Se borrarán 1 opción/);
  await confirm.locator('[data-testid=modifier-groups-delete-submit]').click();
  await expect(groupRow(page, group.id)).toHaveCount(0);
  expect((await api(context, A, 'GET', `/modifier/groups/detail?id=${group.id}`)).status).toBe(404);
});

test('MODIFIER-F01: the employee reads the groups and their sheet, with nothing that changes them', async ({ browser }) => {
  // Made by the owner, through the API (setup, never the check).
  const owner = await hostPage(browser, A, { next: '/modifier/groups' });
  const made = await api<Group>(owner.context, A, 'POST', '/modifier/groups', { name: `E2E Doneness ${STAMP}`, min_choices: 1, max_choices: 1 });
  expect(made.status).toBe(201);
  expect((await api(owner.context, A, 'POST', '/modifier/options', { group_id: made.data.id, name: 'Rare' })).status).toBe(201);
  const employee = await hostPage(browser, A, { next: '/modifier/groups', credentials: EMPLOYEE });
  const { page } = employee;
  try {
    // Positive control: the owner has what the employee must not.
    await tableReady(owner.page);
    await expect(shown(owner.page).locator('[data-testid=modifier-groups-add]')).toBeVisible();

    await tableReady(page);
    await shown(page).locator('[data-testid=modifier-groups-search] input').fill(STAMP);
    await expect(groupRow(page, made.data.id)).toBeVisible();
    await expect(shown(page).locator('[data-testid=modifier-groups-add]')).toHaveCount(0);
    await expect(shown(page).locator(`[data-testid=modifier-groups-row-${made.data.id}-delete]`)).toHaveCount(0);
    await groupRow(page, made.data.id).locator('[role=cell]').first().click();
    await expect(sheet(page)).toBeVisible();
    await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-row-]')).toContainText('Rare');
    for (const hook of ['modifier-sheet-options-add', 'modifier-sheet-links-add']) {
      await expect(sheet(page).locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
    }
    await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-delete-]')).toHaveCount(0);
    // The API refuses the write too.
    const refused = await api<{ error: { code: string } }>(employee.context, A, 'POST', '/modifier/groups', { name: `E2E Nope ${STAMP}` });
    expect([refused.status, refused.data.error.code]).toEqual([403, 'permission_denied']);
    await page.screenshot({ path: shot('modifier-employee-sheet') });
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});
