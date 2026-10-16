// Shared steps of the task e2e (task-*.spec.ts): a signed-in page in English, the apps' APIs for setup
// and server-side evidence (never the check itself), a Combo pick, a row action (a button, or inside «⋮»
// when the row folds them) and the cleanup every spec runs before and after it: what a run creates is
// named «E2E Task …» (projects `e2e-…`) and deleted from the hub's database (phase 1: `a` and `b` share it).
import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, type Credentials, login, psql, shown } from './helpers';

/** Every name a task spec gives starts like this. */
export const TAG = 'E2E Task';

/** `E2E Task <label> <base36 time>`: unique per run. */
export const named = (label: string): string => `${TAG} ${label} ${Date.now().toString(36)}`;

export const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 820, height: 1180 },
  phone: { width: 390, height: 844 },
} as const;

export async function signedIn(
  browser: Browser,
  next: string,
  credentials?: Credentials,
  viewport: { width: number; height: number } = VIEWPORTS.desktop,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** POST to the hub's API with the page's session; fails the test on anything but `status`. */
export async function post<T>(context: BrowserContext, path: string, body: unknown, status = 201): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`. */
export async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  await input.click();
  await input.fill(query);
  await page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first().click();
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

/** The row of a table that holds `text`. */
export const rowOf = (page: Page, table: string, text: string) =>
  shown(page).locator(`[data-testid=${table}-row]`, { hasText: text });

/** Deletes everything a task spec created: tasks (with their comments), projects and staff records. */
export function cleanUp(): void {
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  const tasks = `select id from task_task where title like '${TAG}%' or assigned_to_id in (${members})`;
  psql(
    [
      `delete from task_comment where task_id in (${tasks})`,
      `update task_task set parent_id = null where parent_id in (${tasks})`,
      `delete from task_task where title like '${TAG}%' or assigned_to_id in (${members})`,
      `delete from task_project where code like 'e2e-%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}
