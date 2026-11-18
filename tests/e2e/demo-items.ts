// The demo app's items as the specs make and read them: their names, through the API and on the list.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { api } from './hub-api';
import { shown } from './screen';

export interface Item {
  id: string;
  name: string;
  status: 'open' | 'done';
  note: string;
}

export const uniqueName = (prefix: string): string => `${prefix} ${Date.now().toString(36)}`;

export async function createItem(context: BrowserContext, origin: string, name: string): Promise<Item> {
  const res = await api<Item>(context, origin, 'POST', '/demo/items', { name });
  expect(res.status, `create ${name}`).toBe(201);
  return res.data;
}

export async function itemDetail(
  context: BrowserContext,
  origin: string,
  id: string,
): Promise<Item & { lines: { text: string; client_line_id: string | null }[] }> {
  const res = await api<Item & { lines: { text: string; client_line_id: string | null }[] }>(
    context,
    origin,
    'GET',
    `/demo/items/detail?id=${id}`,
  );
  expect(res.status).toBe(200);
  return res.data;
}

/** Deletes every demo item, through the API. */
export async function clearItems(context: BrowserContext, origin: string): Promise<number> {
  let deleted = 0;
  for (;;) {
    const page = await api<{ rows: { id: string }[] }>(context, origin, 'GET', '/demo/items?limit=100');
    if (page.data.rows.length === 0) return deleted;
    for (const row of page.data.rows) {
      const res = await api(context, origin, 'POST', '/demo/items/delete', { id: row.id });
      expect(res.status).toBeLessThan(300);
      deleted += 1;
    }
  }
}

/** Waits until the list painted its first result (empty state or rows). */
export async function listReady(page: Page): Promise<void> {
  await shown(page)
    .locator('[data-testid=demo-items-empty], [data-testid=demo-items-row]')
    .first()
    .waitFor({ state: 'visible' });
}

export async function rowNames(page: Page): Promise<string[]> {
  return shown(page).locator('[data-testid=demo-item-name]').allInnerTexts();
}

export const row = (page: Page, name: string): Locator =>
  shown(page).locator('[data-testid=demo-items-row]', { has: page.getByText(name, { exact: true }) });

/** The row (or card) of the item `id` on the list shown. */
export const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=demo-items-row][data-id="${id}"]`);

/** From the list: «New item» → `/demo/items/new`, types the name and arms a click-time probe on
 *  «Save» (not clicked yet): `__saveClickedAt` (`Date.now()`) and `__saveClickedPageMs` (`performance.now()`, the
 *  page's clock, which Resource Timing uses). */
export async function fillNewItem(page: Page, name: string): Promise<Locator> {
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await page.waitForURL(/\/demo\/items\/new$/);
  const form = shown(page).locator('[data-testid=demo-form]');
  await form.locator('[data-testid=demo-form-name] input').fill(name);
  const save = form.locator('[data-testid=demo-form-save]');
  await save.evaluate((el) => {
    const w = window as unknown as Record<string, number>;
    el.addEventListener(
      'click',
      () => {
        w.__saveClickedAt = Date.now();
        w.__saveClickedPageMs = performance.now();
      },
      { capture: true, once: true },
    );
  });
  return save;
}

/** Creates an item through the «New item» page and waits until it is back on the list. */
export async function createViaPage(page: Page, name: string): Promise<void> {
  const save = await fillNewItem(page, name);
  await save.click();
  await page.waitForURL(/\/demo\/items$/, { timeout: 10_000 });
  await listReady(page);
}

/** In-page probe: the `Date.now()` at which a row named `name` shows up (read by `appearedAt`). */
export async function watchForRow(page: Page, name: string): Promise<void> {
  await page.evaluate((wanted) => {
    const w = window as unknown as { __rowSeen?: Record<string, number> };
    w.__rowSeen ??= {};
    const seen = w.__rowSeen;
    const check = (): boolean => {
      const found = [...document.querySelectorAll('[data-testid=demo-item-name]')].some(
        (el) => el.textContent?.trim() === wanted,
      );
      if (found && seen[wanted] === undefined) seen[wanted] = Date.now();
      return found;
    };
    if (check()) return;
    const observer = new MutationObserver(() => {
      if (check()) observer.disconnect();
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }, name);
}

export async function appearedAt(page: Page, name: string): Promise<number | undefined> {
  return page.evaluate((wanted) => (window as unknown as { __rowSeen?: Record<string, number> }).__rowSeen?.[wanted], name);
}
