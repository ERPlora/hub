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
//   - BASE-G109: Reset › «Reset the business»: the plan per section, one box each, and its red button off until one is
//     ticked (`a` has its own database since S2a, round 2026-10-30 of PLAN-DB; one that shares control's says why it
//     cannot be emptied: ResetPanel.test.ts). Nothing is reset: the business stays for the other specs;
//   - BASE-F37: «Copies», the full copies of the business's data made before each reset (S2b): none in `a`.
// The business is emptied first through the apps' own operations (phase 1: `a` and `b` shared their rows, as
// `clearItems` does with the demo's). Each flow leaves its capture `APP-BASE-2-<flow>-<width>`.
// flow: BASE-F37 BASE-G101 BASE-G102 BASE-G103 BASE-G104 BASE-G105 BASE-G106 BASE-G107 BASE-G108 BASE-G109 BASE-G131
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, type Page, test } from '@playwright/test';

import { A, api, ARTIFACTS, emptyOfTemplateData, horizontalOverflow, hostPage, shot, shown, untilStill } from './helpers';

// A control that never comes fails in half a minute and says which, instead of eating the whole test.
test.use({ actionTimeout: 30_000 });

// Once the tests are over (a failed one included), `a` is emptied again of what the templates loaded here brought, as
// the run found it: every later spec uses the same business (hub#529: SALE-F12's «All» started with a service, and
// the website's catalogue showed six categories instead of two). template-data.test.ts keeps every such spec at it.
test.afterAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/' });
  try {
    await emptyOfTemplateData(context, A);
  } finally {
    await context.close();
  }
});

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

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
  const overflow = await horizontalOverflow(page);
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
    await emptyOfTemplateData(context, A);

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

    // BASE-G109 — the plan per section, a box each, and «Reset the business» off until one is ticked (never pressed).
    const first = testid(page, 'reset-section').first();
    await expect(first).toBeVisible();
    await expect(testid(page, 'reset-shared')).toHaveCount(0);
    const submit = testid(page, 'reset-submit');
    await expect(submit).toHaveAttribute('disabled');
    const box = first.locator('ion-checkbox');
    await box.click();
    await expect(submit).not.toHaveAttribute('disabled');
    await box.click();
    await expect(submit).toHaveAttribute('disabled');
    await submit.scrollIntoViewIfNeeded();
    await snap(page, 'BASE-G109', width);

    // BASE-F37 — «Copies»: what a copy of the data is next to «Export»; `a` was never reset, so it has none (S2b).
    await expect(testid(page, 'dumps-intro')).toContainText('keeps it for 90 days');
    await expect(testid(page, 'dumps-empty')).toContainText('No copies yet');
    await testid(page, 'dumps-card').scrollIntoViewIfNeeded();
    await snap(page, 'BASE-F37-copies', width);

    await context.close();
  });
}
