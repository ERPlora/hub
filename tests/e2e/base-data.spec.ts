// Settings › Data and backups and the Home's templates card (APP-BASE-2; the old hub's settings-data-*.png and
// dashboard-*.png) in the three viewports, as the owner of hub `a`, end to end against the real apps:
//   - BASE-G131: in an empty business the Home offers «Start with a business like yours»; «Use this one» loads the
//     template and the Home is up to date without a reload («Finish setting up your business» counts the catalogue);
//   - BASE-G103, G105, G106: Settings › Data › Import, a template of the catalogue reviewed and loaded again: what was
//     already there stays («You had it already»);
//   - BASE-G101, G102: Export, the data of Inventory without one of its tables, saved as a file;
//   - BASE-G104, G106, G107: a file uploaded by hand with a row an app refuses: «Applied in part» with the reason, and on
//     coming back to Import, that last report first, with «Retry what is missing» off and why;
//   - BASE-G108: Reset › «Undo an import», confirmed, with what was removed;
//   - BASE-G109: Reset › «Reset the business»: the plan per section and, in phase 1 (one database for every hub), why
//     it cannot be emptied, with no red button.
// The business is emptied first through the apps' own operations (phase 1: `a` and `b` share their rows, as
// `clearItems` does with the demo's). Each flow leaves its capture `APP-BASE-2-<flow>-<width>`.
// flow: BASE-G101 BASE-G102 BASE-G103 BASE-G104 BASE-G105 BASE-G106 BASE-G107 BASE-G108 BASE-G109 BASE-G131
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, ARTIFACTS, hostPage, shot, shown, untilStill } from './helpers';

// A control that never comes fails in half a minute and says which, instead of eating the whole test.
test.use({ actionTimeout: 30_000 });

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** What a template brings, last first (tables before their zones, products before their categories), each with
 * the operation's route that lists it and the one that takes a row away: the server's own (`base.blueprint`). */
const TEMPLATE_DATA = [
  ['/table/tables', '/table/tables/delete'],
  ['/table/zones', '/table/zones/delete'],
  ['/service/services', '/service/services/archive'],
  ['/service/categories', '/service/categories/delete'],
  ['/inventory/products', '/inventory/products/delete'],
  ['/inventory/categories', '/inventory/categories/delete'],
] as const;

/** Takes away every row a template brings, through the apps' operations, until the server says the business is empty. */
async function emptyBusiness(context: BrowserContext): Promise<void> {
  for (let pass = 0; pass < 5; pass += 1) {
    for (const [list, remove] of TEMPLATE_DATA) {
      const rows = await api<{ rows: { id: string }[] }>(context, A, 'GET', `${list}?limit=100&offset=0`);
      expect(rows.status, list).toBe(200);
      for (const row of rows.data.rows) {
        const res = await api(context, A, 'POST', remove, { id: row.id });
        expect(res.status, `${remove} ${row.id}`).toBeLessThan(300);
      }
    }
    const catalogue = await api<{ empty: boolean }>(context, A, 'GET', '/settings/data/blueprints');
    if (catalogue.data.empty) return;
  }
  throw new Error('the business could not be emptied of what a template brings');
}

/** A .blueprint.zip with two products of Inventory, the second with a price no app takes: it loads in part. */
function partialFile(stamp: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  const path = join(ARTIFACTS, `partial-${stamp}.blueprint.zip`);
  const manifest = {
    format: 'erplora.blueprint',
    format_version: 1,
    name: `E2E partial ${stamp}`,
    language: 'en',
    country: 'ES',
    purpose: 'template',
    created_at: new Date().toISOString(),
    vertical: 'restaurant',
    version: '',
    apps: ['inventory'],
  };
  const product = (name: string, sku: string, price: unknown) => ({
    name,
    sku,
    price,
    cost: 0,
    stock: '',
    low_stock_threshold: '0',
    unit: 'ud',
    ean13: '',
    description: '',
    tax_category_key: 'restaurant.food',
    categories: [],
    track_stock: false,
    is_active: true,
  });
  const products = [product(`E2E good ${stamp}`, `E2G-${stamp}`, 500), product(`E2E broken ${stamp}`, `E2B-${stamp}`, 'abc')];
  const script = [
    'import json, sys, zipfile',
    'path, manifest, products = sys.argv[1], sys.argv[2], sys.argv[3]',
    "with zipfile.ZipFile(path, 'w') as z:",
    "    z.writestr('manifest.json', manifest)",
    "    z.writestr('data/inventory.product.json', products)",
  ].join('\n');
  execFileSync('python3', ['-I', '-c', script, path, JSON.stringify(manifest), JSON.stringify(products)]);
  return path;
}

/** The capture of a flow, once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, flow: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-2-${flow}-${width}`), fullPage: false });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

async function section(page: Page, name: 'import' | 'export' | 'reset'): Promise<void> {
  await testid(page, `data-section-${name}`).click();
  await expect(page).toHaveURL(new RegExp(name === 'import' ? '/settings(\\?data=import)?#data$' : `data=${name}#data$`));
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-G131 BASE-G101–G109 — the templates card and Settings › Data at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    await emptyBusiness(context);

    // BASE-G131 — the card in an empty business; the checklist before loading.
    await page.goto(`${A}/`);
    const card = testid(page, 'blueprint-card');
    await expect(card).toBeVisible();
    await expect(card.locator('[data-testid="blueprint-card-template"]').first()).toBeVisible();
    const progress = testid(page, 'setup-progress');
    await expect(progress).toBeVisible();
    const before = await progress.textContent();
    await snap(page, 'BASE-G131-card', width);
    await card.locator('[data-testid^="blueprint-card-use-"]').first().click();
    await expect(card.locator('[data-testid="blueprint-card-outcome"]')).toContainText('Your apps and your catalogue are ready');
    // The Home is up to date without a reload: the catalogue step counts as done.
    await expect(progress).not.toHaveText(before ?? '');
    await snap(page, 'BASE-G131', width);
    await card.locator('[data-testid="blueprint-card-continue"]').click();
    await expect(card).toHaveCount(0);

    // BASE-G103 — Settings › Data › Import: the catalogue.
    await page.goto(`${A}/settings#data`);
    await expect(testid(page, 'tab-data')).toBeVisible();
    const catalogue = testid(page, 'templates-row').first();
    await expect(catalogue).toBeVisible();
    await snap(page, 'BASE-G103', width);

    // BASE-G105 — review a template; BASE-G106 — load it again: what is there stays.
    await testid(page, 'templates-row').first().locator('[data-testid$="-use"]').click();
    const review = testid(page, 'review');
    await expect(review).toBeVisible();
    await snap(page, 'BASE-G105', width);
    await review.locator('[data-testid="review-import"]').click();
    const report = testid(page, 'report');
    await expect(report.locator('[data-testid="report-status"]')).toContainText('Everything went in.');
    await expect(report.locator('[data-testid="report-app-status"]').first()).toContainText('You had it already');
    await snap(page, 'BASE-G106', width);

    // BASE-G101, BASE-G102 — export Inventory's data without its categories, as a file.
    await section(page, 'export');
    await expect(testid(page, 'export-app').first()).toBeVisible();
    await snap(page, 'BASE-G101', width);
    await testid(page, 'export-data-inventory').click();
    const tables = testid(page, 'export-tables-inventory');
    await expect(tables).toBeVisible();
    await tables.locator('[data-testid="export-table-inventory.category"]').click();
    await snap(page, 'BASE-G102', width);
    const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'export-submit').click()]);
    await expect(testid(page, 'export-done')).toContainText(`${download.suggestedFilename()} downloaded.`);
    const saved = join(ARTIFACTS, `export-${width}-${download.suggestedFilename()}`);
    await download.saveAs(saved);
    expect(readFileSync(saved).subarray(0, 2).toString('latin1')).toBe('PK');

    // BASE-G104, BASE-G106 — a file by hand, with a row an app refuses: in part, and why.
    const stamp = `${width}-${Date.now().toString(36)}`;
    await section(page, 'import');
    await testid(page, 'import-file').setInputFiles(partialFile(stamp));
    await expect(testid(page, 'review')).toBeVisible();
    await snap(page, 'BASE-G104', width);
    await testid(page, 'review-import').click();
    await expect(testid(page, 'report-status')).toContainText('Not everything went in.');
    await expect(testid(page, 'report')).toContainText(`E2E broken ${stamp}`);

    // BASE-G107 — back to Import: that report first, «Retry what is missing» off with why (it came by hand).
    await section(page, 'reset');
    await section(page, 'import');
    await expect(testid(page, 'report-unfinished')).toContainText(`E2E partial ${stamp}`);
    await expect(testid(page, 'report-retry')).toHaveJSProperty('disabled', true);
    await expect(testid(page, 'report-retry-blocked')).toContainText('uploaded by hand');
    await snap(page, 'BASE-G107', width);
    await testid(page, 'report-templates').click();
    await expect(testid(page, 'templates-row').first()).toBeVisible();

    // BASE-G108 — undo that file's load: the product it created goes.
    const good = () =>
      api<{ rows: { name: string }[] }>(context, A, 'GET', `/inventory/products?limit=100&offset=0&search=${encodeURIComponent(`E2E good ${stamp}`)}`);
    expect((await good()).data.rows.map((row) => row.name)).toEqual([`E2E good ${stamp}`]);
    await section(page, 'reset');
    const undoRow = testid(page, 'undo-row').filter({ hasText: `E2E partial ${stamp}` });
    await expect(undoRow).toBeVisible();
    await undoRow.locator('ion-button').click();
    const confirm = page.locator('ion-modal[data-testid="undo-confirm"]');
    await expect(confirm).toBeVisible();
    await snap(page, 'BASE-G108-confirm', width);
    await confirm.locator('[data-testid="undo-confirm-submit"]').click();
    await expect(testid(page, 'undo-result')).toContainText('Inventory — 1 row removed');
    expect((await good()).data.rows).toEqual([]);
    await snap(page, 'BASE-G108', width);

    // BASE-G109 — the plan per section and, in phase 1, why the business cannot be emptied.
    await expect(testid(page, 'reset-section').first()).toBeVisible();
    await expect(testid(page, 'reset-shared')).toContainText('Your business still shares its database with others');
    await expect(testid(page, 'reset-submit')).toHaveCount(0);
    await testid(page, 'reset-shared').scrollIntoViewIfNeeded();
    await snap(page, 'BASE-G109', width);

    await context.close();
  });
}
