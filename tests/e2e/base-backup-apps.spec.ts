// flow: BASE-F35, BASE-F36, BASE-F30, BASE-F31, BASE-F37 — a backup of the business takes what Modifiers, Menus and
// combos and Taxes have, on hub `a` with the real Inventory: in Settings › Data › Export none of the three rows says
// «Nothing of its own to copy» and their data show «Modifier groups», «Menus» and «Own tax categories» with their rows;
// the file downloaded carries the group with its options and the product it applies to, and the menu with its course
// and the product to choose, by its code; loaded again from Import once both are deleted, they come back as they were.
// The business's own tax category, which cannot be deleted, comes back in business `b` from the same file, and Reset
// offers no Taxes section. Each screen in 390×844, 834×1112 and 1440×900. Its data are named `E2E Backup …` /
// `E2E-BAK-…` / `e2e_bak.…` and `afterAll` deletes exactly them, in `a` and `b`. In Spanish too, at each size:
// «Grupos de suplementos», «Menús» and «Categorías fiscales propias», never «Nada propio que copiar».
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  A,
  api,
  B,
  ARTIFACTS,
  capture,
  horizontalOverflow,
  hostPage,
  psql,
  shown,
  signedInSpanish,
  testid,
  THREE_SIZES,
  untilStill,
} from './helpers';

test.use({ actionTimeout: 30_000 });

const STAMP = Date.now().toString(36).toUpperCase();
const SKU = `E2E-BAK-${STAMP}`;
const GROUP = `E2E Backup Doneness ${STAMP}`;
const MENU = `E2E Backup Menu ${STAMP}`;
const OPTIONS = ['Rare', 'Well done'];
const TAX = `e2e_bak.t${STAMP.toLowerCase()}`;

const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E Backup %'";
const OWN_MENUS = "select id from combo_combo where name like 'E2E Backup %'";
const OWN_PRODUCTS = "select id from inventory_product where sku like 'E2E-BAK-%'";
const OWN_TAXES = "select id from tax_taxcategory where key like 'e2e_bak.%'";

function cleanUp(hub = 'a'): void {
  psql(
    [
      `delete from tax_taxrule where category_id in (${OWN_TAXES}) and parent_id is not null`,
      `delete from tax_taxrule where category_id in (${OWN_TAXES})`,
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS}) or product_id in (${OWN_PRODUCTS})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      "delete from modifier_modifiergroup where name like 'E2E Backup %'",
      `delete from combo_choiceoption where product_id in (${OWN_PRODUCTS})`,
      `delete from combo_choicegroup where combo_id in (${OWN_MENUS})`,
      "delete from combo_combo where name like 'E2E Backup %'",
      `delete from inventory_stockmovement where product_id in (${OWN_PRODUCTS})`,
      `delete from inventory_productcategory where product_id in (${OWN_PRODUCTS})`,
      "delete from inventory_product where sku like 'E2E-BAK-%'",
      "delete from tax_taxcategory where key like 'e2e_bak.%'",
    ].join('; '),
    hub,
  );
}

interface Group {
  id: string;
  option_count: number;
  link_count: number;
}

interface Menu {
  id: string;
  groups: { name: string; options: { sku: string }[] }[];
}

/** Each app the spec exports: the row of Export, its part, what it reads back and how it deletes it. */
const APPS = {
  modifier: {
    part: 'modifier.group',
    detail: `/modifier/groups/detail?group=${encodeURIComponent(GROUP)}`,
    remove: '/modifier/groups/delete',
  },
  combo: {
    part: 'combo.combo',
    detail: `/combo/combos/detail?combo=${encodeURIComponent(MENU)}`,
    remove: '/combo/combos/delete',
  },
} as const;
type App = keyof typeof APPS | 'tax';
const PARTS: Record<App, string> = { modifier: 'modifier.group', combo: 'combo.combo', tax: 'tax.category' };

async function make(context: BrowserContext): Promise<void> {
  const group = await api<Group>(context, A, 'POST', '/modifier/groups', { name: GROUP, min_choices: 1, max_choices: 1 });
  expect(group.status).toBe(201);
  for (const [index, name] of OPTIONS.entries()) {
    const option = { group_id: group.data.id, name, price_delta: 0, sort_order: index + 1 };
    expect((await api(context, A, 'POST', '/modifier/options', option)).status).toBe(201);
  }
  expect((await api(context, A, 'POST', '/modifier/links/attach', { group_id: group.data.id, product: SKU })).status).toBe(201);
  expect((await api(context, A, 'POST', '/combo/combos', { name: MENU, price: 1450, supply_kind: 'goods' })).status).toBe(201);
  expect((await api(context, A, 'POST', '/combo/groups', { combo: MENU, name: 'Main' })).status).toBe(201);
  expect((await api(context, A, 'POST', '/combo/options', { combo: MENU, group: 'Main', product: SKU })).status).toBe(201);
  expect((await api(context, A, 'POST', '/tax/categories', { key: TAX, name: `E2E Backup Books ${STAMP}` })).status).toBe(201);
  const rate = { country_code: 'ES', tax_category_key: TAX, rate_pct: '4' };
  expect((await api(context, A, 'POST', '/tax/rules', rate)).status).toBe(201);
}

async function now<T>(context: BrowserContext, app: keyof typeof APPS): Promise<{ status: number; data: T }> {
  return api<T>(context, A, 'GET', APPS[app].detail);
}

async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** Settings › Data › Export with the spec's rows there: neither app's row says `nothing` (in the page's language) and,
 *  with their data ticked, each part says its label with its rows. */
async function partsOf(context: BrowserContext, page: Page, nothing: string, labels: Record<App, string>): Promise<void> {
  if ((await now(context, 'modifier')).status !== 200) await make(context);
  await page.goto(`${A}/settings?data=export#data`);
  for (const app of Object.keys(PARTS) as App[]) {
    const row = shown(page).locator(`[data-testid="export-app"][data-id="${app}"]`);
    await expect(row).toBeVisible();
    await expect(row).not.toContainText(nothing);
    await testid(page, `export-data-${app}`).click();
    await expect(shown(page).locator(`[data-testid="export-table-${PARTS[app]}"]`)).toContainText(`${labels[app]} ·`);
  }
  await shown(page).locator('[data-testid="export-table-combo.combo"]').scrollIntoViewIfNeeded();
}

/** The rows of `part` the file `saved` carries. */
function rowsIn(saved: string, part: string): { name: string; [key: string]: unknown }[] {
  return JSON.parse(execFileSync('unzip', ['-p', saved, `data/${part}.json`], { encoding: 'utf8' }));
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/settings#data' });
  const product = await api(owner.context, A, 'POST', '/inventory/products', {
    name: `E2E Backup Burger ${STAMP}`,
    sku: SKU,
    price: 900,
    tax_category_key: 'restaurant.food',
  });
  expect(product.status).toBe(201);
  await owner.context.close();
});

test.afterAll(() => {
  cleanUp();
  cleanUp('b');
});

for (const size of THREE_SIZES) {
  test(`a backup takes the modifier groups and the menus and brings them back at ${size.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await hostPage(browser, A, { viewport: { width: size.width, height: size.height }, next: '/settings#data' });
    await partsOf(context, page, 'Nothing of its own to copy', { modifier: 'Modifier groups', combo: 'Menus', tax: 'Own tax categories' });
    await snap(page, `BASE-F36-backup-apps-${size.label}`);

    const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'export-submit').click()]);
    const saved = join(ARTIFACTS, `backup-apps-${size.label}-${download.suggestedFilename()}`);
    await download.saveAs(saved);
    const group = rowsIn(saved, 'modifier.group').find((row) => row.name === GROUP);
    expect((group?.options as { name: string }[]).map((option) => option.name)).toEqual(OPTIONS);
    expect(group?.products).toEqual([SKU]);
    const menu = rowsIn(saved, 'combo.combo').find((row) => row.name === MENU);
    expect(menu?.courses).toEqual([expect.objectContaining({ name: 'Main', choices: [expect.objectContaining({ product: SKU })] })]);

    const groupBefore = (await now<Group>(context, 'modifier')).data;
    const menuBefore = (await now<Menu>(context, 'combo')).data;
    expect((await api(context, A, 'POST', APPS.modifier.remove, { id: groupBefore.id })).status).toBe(200);
    expect((await api(context, A, 'POST', APPS.combo.remove, { id: menuBefore.id })).status).toBe(200);
    await testid(page, 'data-section-import').click();
    await testid(page, 'import-file').setInputFiles(saved);
    await expect(testid(page, 'review')).toBeVisible();
    await testid(page, 'review-import').click();
    for (const app of Object.keys(APPS)) {
      const loaded = shown(page).locator(`[data-testid="report-app"][data-id="${app}"] [data-testid="report-app-status"]`);
      await expect(loaded).toContainText('Applied');
    }
    await shown(page).locator('[data-testid="report-app"][data-id="modifier"]').scrollIntoViewIfNeeded();
    await snap(page, `BASE-F31-backup-apps-back-${size.label}`);

    const groupAfter = (await now<Group>(context, 'modifier')).data;
    expect([groupAfter.option_count, groupAfter.link_count]).toEqual([groupBefore.option_count, groupBefore.link_count]);
    const menuAfter = (await now<Menu>(context, 'combo')).data;
    expect(menuAfter.groups.map((course) => [course.name, course.options.map((option) => option.sku)])).toEqual(
      menuBefore.groups.map((course) => [course.name, course.options.map((option) => option.sku)]),
    );

    // Taxes: Reset offers no section of it, and the same file brings the own category into business `b`.
    await testid(page, 'data-section-reset').click();
    await expect(shown(page).locator('[data-testid="reset-section"][data-id="modifier"]')).toBeVisible();
    await expect(shown(page).locator('[data-testid="reset-section"][data-id="tax"]')).toHaveCount(0);
    await context.close();
    const other = await hostPage(browser, B, { viewport: { width: size.width, height: size.height }, next: '/settings#data' });
    cleanUp('b');
    await other.page.goto(`${B}/settings?data=import#data`);
    await testid(other.page, 'import-file').setInputFiles(saved);
    await expect(testid(other.page, 'review')).toBeVisible();
    await testid(other.page, 'review-import').click();
    const taxes = shown(other.page).locator('[data-testid="report-app"][data-id="tax"]');
    await expect(taxes.locator('[data-testid="report-app-status"]')).toContainText('Applied');
    await taxes.scrollIntoViewIfNeeded();
    await snap(other.page, `BASE-F31-backup-taxes-other-business-${size.label}`);
    const back = await api<{ key: string; is_system: boolean }>(other.context, B, 'GET', `/tax/categories/detail?key=${TAX}`);
    expect([back.status, back.data.key, back.data.is_system]).toEqual([200, TAX, false]);
    await other.context.close();
  });

  test(`in Spanish, the data say «Grupos de suplementos» and «Menús» at ${size.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/settings#data');
    await partsOf(context, page, 'Nada propio que copiar', {
      modifier: 'Grupos de suplementos',
      combo: 'Menús',
      tax: 'Categorías fiscales propias',
    });
    await expect(testid(page, 'export-tables-combo')).toContainText('Datos de Menús y combos');
    await snap(page, `BASE-F36-backup-apps-es-${size.label}`);
    await context.close();
  });
}
