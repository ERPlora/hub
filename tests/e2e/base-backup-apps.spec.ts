// flow: BASE-F35, BASE-F36, BASE-F30, BASE-F31 — a backup of the business takes what Modifiers and Menus and combos
// have, on hub `a` with the real Inventory: in Settings › Data › Export neither row says «Nothing of its own to copy»
// and their data show «Modifier groups» and «Menus» with their rows; the file downloaded carries the group with its
// options and the product it applies to, and the menu with its course and the product to choose, by its code; loaded
// again from Import once both are deleted, they come back as they were. Each screen in 390×844, 834×1112 and
// 1440×900. Its data are named `E2E Backup …` / `E2E-BAK-…` and `afterAll` deletes exactly them. In Spanish too, at
// each size: «Grupos de suplementos» and «Menús», never «Nada propio que copiar».
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  A,
  api,
  ARTIFACTS,
  horizontalOverflow,
  hostPage,
  psql,
  shot,
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

const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E Backup %'";
const OWN_MENUS = "select id from combo_combo where name like 'E2E Backup %'";
const OWN_PRODUCTS = "select id from inventory_product where sku like 'E2E-BAK-%'";

function cleanUp(): void {
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS}) or product_id in (${OWN_PRODUCTS})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      "delete from modifier_modifiergroup where name like 'E2E Backup %'",
      `delete from combo_choiceoption where product_id in (${OWN_PRODUCTS})`,
      `delete from combo_choicegroup where combo_id in (${OWN_MENUS})`,
      "delete from combo_combo where name like 'E2E Backup %'",
      `delete from inventory_stockmovement where product_id in (${OWN_PRODUCTS})`,
      `delete from inventory_productcategory where product_id in (${OWN_PRODUCTS})`,
      "delete from inventory_product where sku like 'E2E-BAK-%'",
    ].join('; '),
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
type App = keyof typeof APPS;

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
}

async function now<T>(context: BrowserContext, app: App): Promise<{ status: number; data: T }> {
  return api<T>(context, A, 'GET', APPS[app].detail);
}

async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(name), fullPage: false });
}

/** Settings › Data › Export with the spec's rows there: neither app's row says `nothing` (in the page's language) and,
 *  with their data ticked, each part says its label with its rows. */
async function partsOf(context: BrowserContext, page: Page, nothing: string, labels: Record<App, string>): Promise<void> {
  if ((await now(context, 'modifier')).status !== 200) await make(context);
  await page.goto(`${A}/settings?data=export#data`);
  for (const app of Object.keys(APPS) as App[]) {
    const row = shown(page).locator(`[data-testid="export-app"][data-id="${app}"]`);
    await expect(row).toBeVisible();
    await expect(row).not.toContainText(nothing);
    await testid(page, `export-data-${app}`).click();
    await expect(shown(page).locator(`[data-testid="export-table-${APPS[app].part}"]`)).toContainText(`${labels[app]} ·`);
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

test.afterAll(() => cleanUp());

for (const size of THREE_SIZES) {
  test(`a backup takes the modifier groups and the menus and brings them back at ${size.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await hostPage(browser, A, { viewport: { width: size.width, height: size.height }, next: '/settings#data' });
    await partsOf(context, page, 'Nothing of its own to copy', { modifier: 'Modifier groups', combo: 'Menus' });
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
    await context.close();
  });

  test(`in Spanish, the data say «Grupos de suplementos» and «Menús» at ${size.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/settings#data');
    await partsOf(context, page, 'Nada propio que copiar', { modifier: 'Grupos de suplementos', combo: 'Menús' });
    await expect(testid(page, 'export-tables-combo')).toContainText('Datos de Menús y combos');
    await snap(page, `BASE-F36-backup-apps-es-${size.label}`);
    await context.close();
  });
}
