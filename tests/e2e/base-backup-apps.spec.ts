// flow: BASE-F35, BASE-F36, BASE-F30, BASE-F31 — a backup of the business takes Modifiers' groups, on hub `a` with the
// real Inventory: in Settings › Data › Export the Modifiers row no longer says «Nothing of its own to copy» and its data
// show «Modifier groups» with its rows; the file downloaded carries the group with its options and the product it
// applies to, by its code; loaded again from Import once the group is deleted, the group comes back as it was. Each
// screen in 390×844, 834×1112 and 1440×900. Its data are named `E2E Backup …` / `E2E-BAK-…` and `afterAll` deletes
// exactly them. In Spanish too, at each size: «Grupos de suplementos», never «Nada propio que copiar».
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
const OPTIONS = ['Rare', 'Well done'];

const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E Backup %'";
const OWN_PRODUCTS = "select id from inventory_product where sku like 'E2E-BAK-%'";

function cleanUp(): void {
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS}) or product_id in (${OWN_PRODUCTS})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      "delete from modifier_modifiergroup where name like 'E2E Backup %'",
      `delete from inventory_stockmovement where product_id in (${OWN_PRODUCTS})`,
      `delete from inventory_productcategory where product_id in (${OWN_PRODUCTS})`,
      "delete from inventory_product where sku like 'E2E-BAK-%'",
    ].join('; '),
  );
}

interface Group {
  id: string;
  name: string;
  option_count: number;
  link_count: number;
}

async function makeGroup(context: BrowserContext): Promise<void> {
  const group = await api<Group>(context, A, 'POST', '/modifier/groups', { name: GROUP, min_choices: 1, max_choices: 1 });
  expect(group.status).toBe(201);
  for (const [index, name] of OPTIONS.entries()) {
    const option = { group_id: group.data.id, name, price_delta: 0, sort_order: index + 1 };
    expect((await api(context, A, 'POST', '/modifier/options', option)).status).toBe(201);
  }
  expect((await api(context, A, 'POST', '/modifier/links/attach', { group_id: group.data.id, product: SKU })).status).toBe(201);
}

async function groupNow(context: BrowserContext): Promise<{ status: number; data: Group }> {
  return api<Group>(context, A, 'GET', `/modifier/groups/detail?group=${encodeURIComponent(GROUP)}`);
}

async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(name), fullPage: false });
}

/** Settings › Data › Export with the group there: Modifiers' row does not say `nothing` (in the page's language) and,
 *  with its data ticked, its part says `part` with its rows. */
async function modifiersPart(context: BrowserContext, page: Page, texts: { nothing: string; part: string }): Promise<void> {
  if ((await groupNow(context)).status !== 200) await makeGroup(context);
  await page.goto(`${A}/settings?data=export#data`);
  const modifiers = shown(page).locator('[data-testid="export-app"][data-id="modifier"]');
  await expect(modifiers).toBeVisible();
  await expect(modifiers).not.toContainText(texts.nothing);
  await testid(page, 'export-data-modifier').click();
  const part = shown(page).locator('[data-testid="export-table-modifier.group"]');
  await expect(part).toContainText(`${texts.part} ·`);
  await part.scrollIntoViewIfNeeded();
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
  test(`a backup takes the modifier groups and brings them back at ${size.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await hostPage(browser, A, { viewport: { width: size.width, height: size.height }, next: '/settings#data' });
    await modifiersPart(context, page, { nothing: 'Nothing of its own to copy', part: 'Modifier groups' });
    await snap(page, `BASE-F36-modifier-groups-${size.label}`);

    const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'export-submit').click()]);
    const saved = join(ARTIFACTS, `backup-modifiers-${size.label}-${download.suggestedFilename()}`);
    await download.saveAs(saved);
    const groups = JSON.parse(execFileSync('unzip', ['-p', saved, 'data/modifier.group.json'], { encoding: 'utf8' }));
    const mine = groups.find((row: { name: string }) => row.name === GROUP);
    expect(mine.options.map((option: { name: string }) => option.name)).toEqual(OPTIONS);
    expect(mine.products).toEqual([SKU]);

    const before = (await groupNow(context)).data;
    expect((await api(context, A, 'POST', '/modifier/groups/delete', { id: before.id })).status).toBe(200);
    await testid(page, 'data-section-import').click();
    await testid(page, 'import-file').setInputFiles(saved);
    await expect(testid(page, 'review')).toBeVisible();
    await testid(page, 'review-import').click();
    const loaded = shown(page).locator('[data-testid="report-app"][data-id="modifier"] [data-testid="report-app-status"]');
    await expect(loaded).toContainText('Applied');
    await loaded.scrollIntoViewIfNeeded();
    await snap(page, `BASE-F31-modifier-groups-back-${size.label}`);

    const after = (await groupNow(context)).data;
    expect([after.option_count, after.link_count]).toEqual([before.option_count, before.link_count]);
    await context.close();
  });

  test(`in Spanish, Modifiers' data say «Grupos de suplementos» at ${size.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/settings#data');
    await modifiersPart(context, page, { nothing: 'Nada propio que copiar', part: 'Grupos de suplementos' });
    await expect(testid(page, 'export-tables-modifier')).toContainText('Datos de Suplementos');
    await snap(page, `BASE-F36-modifier-groups-es-${size.label}`);
    await context.close();
  });
}
