// Taxes → Rules in Chrome (TAX-F03, F04, F07, F08, F11; apps/tax/WORKBOOK.md), on a category of its
// own (categories are never deleted, so each run makes a fresh one through the API):
//   - «+» → «New tax rule»: Spain, the category, 10 % from 2026-01-01 → the row arrives live;
//   - the same slot from 2026-06-01 again: the overlap refused under «Valid from» (409, visible);
//   - «Set end date» 2026-05-31 on the first, then the new rate from 2026-06-01 goes through;
//   - the jurisdiction filter (Country, Region) narrows to the Canary Islands rule;
//   - «Deactivate» (confirmed) takes it off the list; Status «Deactivated» shows it with «Restore»;
//   - a phone (390×844) shows the rules as cards. Screenshots of each step and of the 3 viewports.
// What it creates is deleted after the file (`afterAll`).
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

/** Categories are never deleted by the app: what this file made goes with the database's own hand
 *  (the hub `a`'s), components first, then rules, aliases and the categories. */
const CLEANUP = [
  "delete from tax_taxalias where category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxrule where parent_id is not null and category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxrule where category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxcategory where key like 'e2e.%'",
].join('; ');

test.afterAll(() => {
  psql(CLEANUP);
});

/** No horizontal scroll: the page is not wider than the window (polled while the layout settles). */
async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

interface Rule {
  id: string;
  valid_to: string | null;
}

/** A fresh category of this run, created through the API (setup, not the check). */
async function freshCategory(context: BrowserContext, prefix: string): Promise<string> {
  const key = `e2e.${prefix}_${Date.now().toString(36)}`;
  const res = await api(context, A, 'POST', '/tax/categories', { key, name: `E2E ${prefix} ${key.slice(-6)}` });
  expect(res.status, `create category ${key}`).toBe(201);
  return key;
}

async function rulesOf(context: BrowserContext, key: string, status = 'all'): Promise<Rule[]> {
  const res = await api<{ rows: Rule[] }>(context, A, 'GET', `/tax/rules?tax_category_key=${key}&status=${status}&limit=100`);
  expect(res.status).toBe(200);
  return res.data.rows;
}

/** Types `text` in a searchable field (a Combo) and picks the option `value` from its list. */
async function choose(page: Page, field: Locator, testid: string, text: string, value: string): Promise<void> {
  const input = field.locator('input').first();
  await input.click();
  await input.fill(text);
  await page.locator(`[data-testid="${testid}-option-${value}"]`).click();
  await expect(page.locator(`[data-testid="${testid}-option-${value}"]`)).toHaveCount(0);
}

/** Opens an `ion-select` and picks the option whose text is `text` (popover interface). */
async function pick(page: Page, select: Locator, text: string | RegExp): Promise<void> {
  await select.click();
  const popover = page.locator('ion-popover').last();
  await popover.waitFor({ state: 'visible' });
  await popover.locator('ion-radio, ion-item').filter({ hasText: text }).first().click();
  await expect(popover).toBeHidden();
}

const rows = (page: Page) => shown(page).locator('[data-testid=tax-rules-row]');

async function listReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=tax-rules-row], [data-testid=tax-rules-empty]').first().waitFor({ state: 'visible' });
}

/** Narrows the list to `key` with the search box (it matches the category). */
async function searchFor(page: Page, key: string): Promise<void> {
  await shown(page).locator('[data-testid=tax-rules-search] input').fill(key);
  await expect(rows(page).first()).toContainText(key);
}

async function fillRule(page: Page, dialog: Locator, key: string, rate: string, from: string): Promise<void> {
  await choose(page, dialog.locator('[data-testid=tax-rule-form-country_code]'), 'tax-rule-form-country_code', 'Spain', 'ES');
  await choose(page, dialog.locator('[data-testid=tax-rule-form-tax_category_key]'), 'tax-rule-form-tax_category_key', key, key);
  await dialog.locator('[data-testid=tax-rule-form-rate_pct] input').fill(rate);
  await dialog.locator('[data-testid=tax-rule-form-valid_from] input').fill(from);
}

test('TAX-F04/F07: a rule is created, an overlapping one is refused on «Valid from», ending the first lets the new rate in', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'rule');
  await listReady(page);

  // 1. «+» → «New tax rule»: Spain, the category, 10 % from 2026-01-01.
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  const dialog = page.locator('ion-modal[data-testid=tax-rule-form]');
  await expect(dialog).toBeVisible();
  await fillRule(page, dialog, key, '10', '2026-01-01');
  await page.screenshot({ path: shot('tax-rules-new-1280') });
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, key);
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText('10.00%');
  await expect(rows(page).first()).toContainText('Jan 1, 2026');

  // 2. The same slot from 2026-06-01, the first still open-ended: refused on «Valid from» (409).
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  await fillRule(page, dialog, key, '21', '2026-06-01');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  const validFrom = dialog.locator('[data-testid=tax-rule-form-valid_from]');
  await expect(validFrom).toHaveClass(/ion-invalid/);
  await expect(validFrom.locator('.error-text')).toContainText(/overlaps another active rule|Se solapa con otra regla/);
  await expect(dialog.locator('[data-testid=tax-rule-form-error]')).toBeVisible();
  await page.screenshot({ path: shot('tax-rules-overlap-409-1280') });
  await dialog.locator('[data-testid=tax-rule-form-cancel]').click();
  await expect(dialog).toBeHidden();
  expect(await rulesOf(context, key)).toHaveLength(1);

  // 3. «Set end date» 2026-05-31 on the rule in force.
  const [first] = await rulesOf(context, key);
  await shown(page).locator(`[data-testid=tax-rules-row-${first.id}-end]`).click();
  const end = page.locator('ion-modal[data-testid=tax-rule-end]');
  await expect(end).toBeVisible();
  await end.locator('[data-testid=tax-rule-end-valid_to] input').fill('2026-05-31');
  await page.screenshot({ path: shot('tax-rules-end-1280') });
  await end.locator('[data-testid=tax-rule-end-submit]').click();
  await expect(end).toBeHidden();
  await expect(rows(page).first()).toContainText('May 31, 2026');

  // 4. Now the new rate from 2026-06-01 goes through: two rows, one after the other.
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  await fillRule(page, dialog, key, '21', '2026-06-01');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await expect(rows(page)).toHaveCount(2);
  await page.screenshot({ path: shot('tax-rules-changed-rate-1280') });
  const saved = await rulesOf(context, key);
  expect(saved.map((r) => r.valid_to).sort()).toEqual(['2026-05-31', null].sort());
});

test('TAX-F11/F03: the jurisdiction filter narrows to the Canary Islands rule; deactivated rules are reached by Status and restored', async ({
  page,
  context,
}) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'canary');
  for (const body of [
    { country_code: 'ES', tax_category_key: key, rate_pct: 21 },
    { country_code: 'ES', region_code: 'ES-CN', tax_category_key: key, rate_pct: 7, tax_type: 'igic' },
  ]) {
    const res = await api(context, A, 'POST', '/tax/rules', body);
    expect(res.status, JSON.stringify(res.data)).toBe(201);
  }
  await listReady(page);
  await searchFor(page, key);
  await expect(rows(page)).toHaveCount(2);

  // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  // The table's funnel → Country Spain, Region «CN», «Apply»: only the Canary Islands rule.
  await shown(page).locator('[data-testid=tax-rules-filters-toggle]').click();
  const panel = shown(page).locator('[data-testid=tax-rules-filters-panel]');
  await expect(panel).toBeVisible();
  await pick(page, panel.locator('[data-testid=tax-rules-filter-country_code]'), /^(Spain|España) \(ES\)$/);
  await panel.locator('[data-testid=tax-rules-filter-region_code] input').fill('CN');
  await page.screenshot({ path: shot('tax-rules-filters-1280') });
  await panel.locator('[data-testid=tax-rules-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(shown(page).locator('[data-testid=tax-rules-filters-count]')).toHaveText('2');
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText('ES-CN');
  await expect(rows(page).first()).toContainText(/IGIC/);
  await page.screenshot({ path: shot('tax-rules-canary-1280') });

  // «Deactivate» asks first, then the rule leaves the active list.
  const regional = (await api<{ rows: Rule[] }>(context, A, 'GET', `/tax/rules?tax_category_key=${key}&region_code=CN`)).data.rows[0];
  expect(regional, 'the Canary Islands rule').toBeDefined();
  await shown(page).locator(`[data-testid=tax-rules-row-${regional.id}-deactivate]`).click();
  const confirm = page.locator('ion-modal[data-testid=tax-rule-deactivate]');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText(/Deactivate tax rule|Desactivar regla fiscal/);
  await page.screenshot({ path: shot('tax-rules-deactivate-1280') });
  await confirm.locator('[data-testid=tax-rule-deactivate-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(shown(page).locator('[data-testid=tax-rules-empty]')).toBeVisible();

  // Status «Deactivated»: there it is, with «Restore» (no confirmation).
  await pick(page, shown(page).locator('[data-testid=tax-rules-status]'), /^(Deactivated|Desactivadas)$/);
  await expect(rows(page)).toHaveCount(1);
  const restore = shown(page).locator(`[data-testid=tax-rules-row-${regional.id}-restore]`);
  await expect(restore).toBeVisible();
  await page.screenshot({ path: shot('tax-rules-deactivated-1280') });
  await restore.click();
  await expect(shown(page).locator('[data-testid=tax-rules-empty]')).toBeVisible();
  expect((await rulesOf(context, key, 'active')).map((r) => r.id)).toContain(regional.id);
});

test('Rules and Aliases in the three viewports: no horizontal scroll; cards on a phone', async ({ page }) => {
  await login(page, A, '/tax/rules');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const section of ['rules', 'aliases'] as const) {
      await page.goto(`${A}/tax/${section}`);
      await shown(page).locator(`[data-testid=tax-${section}-row], [data-testid=tax-${section}-empty]`).first().waitFor({ state: 'visible' });
      await noHorizontalScroll(page, `${section} ${vp.label}`);
      if (vp.width === 390) await expect(shown(page).locator('.data-table__cards')).toBeVisible();
      await page.screenshot({ path: shot(`tax-${section}-${vp.label}`) });
    }
  }
});
