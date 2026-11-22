// Shared steps of the task e2e (task-*.spec.ts): a signed-in page in English, the apps' APIs for setup
// and server-side evidence (never the check itself), a Combo pick and the cleanup every spec runs before and
// after it: what a run creates is named «E2E Task …» (projects `e2e-…`) and deleted from the hub's database.
// A row action is service-helpers.ts's `rowAction`.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, type Credentials, horizontalOverflow, login, psql, shown, untilStill } from './helpers';

/** Every name a task spec gives starts like this. */
export const TAG = 'E2E Task';

/** `E2E Task <label> <base36 time>`: unique per run. */
export const named = (label: string): string => `${TAG} ${label} ${Date.now().toString(36)}`;

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 834, height: 1112 },
  phone: { width: 390, height: 844 },
} as const;

/** The flows' captures, by width: `APP-TASK-<flow>-<width>.png` in the artifacts. */
export const FLOW_VIEWPORTS = { 390: VIEWPORTS.phone, 834: VIEWPORTS.tablet, 1440: VIEWPORTS.desktop } as const;

/**
 * Captures what the page shows for `flow` at `width` once nothing moves (`untilStill`: a sheet or a dialog is
 * still sliding in right after it is «visible», and so is a notice), after checking nothing scrolls sideways.
 */
export async function snap(page: Page, flow: string, width: number | string): Promise<void> {
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `APP-TASK-${flow}-${width}`);
}

/** Chooses `label` in an `ion-select` that opens as a popover. */
export async function choose(page: Page, select: Locator, label: string): Promise<void> {
  await select.click();
  const popover = page.locator('ion-popover.select-popover');
  await popover.locator('ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  await expect(popover).toHaveCount(0);
}

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
  // Choosing closes the list: nothing of it is left over the next field.
  await expect(page.locator(`[data-testid^=${testid}-option-]`)).toHaveCount(0);
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
