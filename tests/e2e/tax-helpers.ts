// What the tax e2e specs share (apps/tax/WORKBOOK.md): the three sizes a flow is seen at, the
// screenshot of each, the cleanup of what a run made (categories are never deleted by the app), the
// API setup of a fresh category and its rules, and the pickers of the tax screens (a Combo, an
// `ion-select` popover, a row action inline or behind the row's «⋮»).
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, psql, shown } from './helpers';

/** 390×844, 834×1112 and 1440×900: a phone, a tablet and a desk. */
export const FLOW_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

export type Section = 'categories' | 'rules' | 'aliases';

/** What a run made goes with the database's own hand (the hub `a`'s): components first, then rules,
 *  aliases and the categories, all under the `e2e.` keys and the `e2e ` aliases. */
export function cleanUp(): void {
  psql(
    [
      "delete from tax_taxalias where alias like 'e2e %' or category_id in (select id from tax_taxcategory where key like 'e2e.%')",
      "delete from tax_taxrule where parent_id is not null and category_id in (select id from tax_taxcategory where key like 'e2e.%')",
      "delete from tax_taxrule where category_id in (select id from tax_taxcategory where key like 'e2e.%')",
      "delete from tax_taxcategory where key like 'e2e.%'",
    ].join('; '),
  );
}

/** How many pixels the shown page scrolls sideways (0 when everything fits its width). */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as
      | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })
      | null;
    const inner = content?.getScrollElement ? await content.getScrollElement() : null;
    const outer = document.documentElement.scrollWidth - window.innerWidth;
    const own = inner ? inner.scrollWidth - inner.clientWidth : 0;
    return Math.max(outer, own);
  });
}

/** At each of the three sizes: `target` in sight, no sideways scroll, and `APP-TAX-<key>-<width>.png`. */
export async function threeShots(page: Page, key: string, target: () => Locator): Promise<void> {
  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // A list turns its rows into cards on a phone: what was there is painted again, so it retries.
    await expect(async () => {
      const seen = target();
      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(seen).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `${key} at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await capture(page, `APP-TAX-${key}-${vp.label}`);
  }
}

/** A fresh category of this run, created through the API (setup, not the check). */
export async function freshCategory(context: BrowserContext, prefix: string): Promise<string> {
  const key = `e2e.${prefix}_${Date.now().toString(36)}`;
  const res = await api(context, A, 'POST', '/tax/categories', { key, name: `E2E ${prefix} ${key.slice(-6)}` });
  expect(res.status, `create category ${key}`).toBe(201);
  return key;
}

export interface Rule {
  id: string;
  parent_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
}

/** Creates a rule through the API (setup) and returns it. */
export async function createRule(context: BrowserContext, body: Record<string, unknown>): Promise<Rule> {
  const res = await api<Rule>(context, A, 'POST', '/tax/rules', body);
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

/** The rules of a category (server-side evidence). */
export async function rulesOf(context: BrowserContext, key: string, status = 'all'): Promise<Rule[]> {
  const res = await api<{ rows: Rule[] }>(context, A, 'GET', `/tax/rules?tax_category_key=${key}&status=${status}&limit=100`);
  expect(res.status).toBe(200);
  return res.data.rows;
}

export const rows = (page: Page, section: Section): Locator => shown(page).locator(`[data-testid=tax-${section}-row]`);

/** Waits for a tax list to paint its first result (rows or its empty state). */
export async function listReady(page: Page, section: Section): Promise<void> {
  await shown(page).locator(`[data-testid=tax-${section}-row], [data-testid=tax-${section}-empty]`).first().waitFor({ state: 'visible' });
}

/** Narrows a tax list with its search box until its first row holds `text`. */
export async function searchFor(page: Page, section: Section, text: string): Promise<void> {
  await shown(page).locator(`[data-testid=tax-${section}-search] input`).fill(text);
  await expect(rows(page, section).first()).toContainText(text);
}

/** Types `text` in a Combo and picks the option `id` from its list. */
export async function pickCombo(page: Page, scope: Locator, testid: string, text: string, id: string): Promise<void> {
  const input = scope.locator(`[data-testid=${testid}] input`).first();
  await input.click();
  await input.fill(text);
  const option = page.locator(`[data-testid="${testid}-option-${id}"]`);
  await option.click();
  await expect(option).toHaveCount(0);
}

/** Opens an `ion-select` (popover interface) and picks the option whose text is `text`. */
export async function pickSelect(page: Page, select: Locator, text: string | RegExp): Promise<void> {
  await select.click();
  const popover = page.locator('ion-popover').last();
  await popover.waitFor({ state: 'visible' });
  await popover.locator('ion-radio, ion-item').filter({ hasText: text }).first().click();
  await expect(popover).toBeHidden();
}

/** Runs a row action of a tax list: its inline button, or the row's «⋮» menu when it folded there. */
export async function rowAction(page: Page, section: Section, id: string, action: string): Promise<void> {
  const hook = `tax-${section}-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=tax-${section}-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}
