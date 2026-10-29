// Shared steps of the task e2e (task-*.spec.ts): a signed-in page in English, the apps' APIs for setup
// and server-side evidence (never the check itself), a Combo pick, a row action (a button, or inside «⋮»
// when the row folds them) and the cleanup every spec runs before and after it: what a run creates is
// named «E2E Task …» (projects `e2e-…`) and deleted from the hub's database (phase 1: `a` and `b` share it).
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, type Credentials, horizontalOverflow, login, psql, shown } from './helpers';

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
 * Counts, in the page, the Ionic modals and popovers still sliding in or out (between their «will» and
 * «did» events): their animations run in shadow roots, out of `document.getAnimations()`.
 */
function countMovingOverlays(): void {
  const page = window as unknown as { __overlaysMoving: number };
  page.__overlaysMoving = 0;
  for (const kind of ['Modal', 'Popover']) {
    for (const [start, end] of [['WillPresent', 'DidPresent'], ['WillDismiss', 'DidDismiss']]) {
      document.addEventListener(`ion${kind}${start}`, () => (page.__overlaysMoving += 1));
      document.addEventListener(`ion${kind}${end}`, () => (page.__overlaysMoving = Math.max(0, page.__overlaysMoving - 1)));
    }
  }
}

/**
 * Captures what the page shows for `flow` at `width` once no modal or popover is moving (a sheet or a
 * dialog is still sliding in right after it is «visible»), after checking nothing scrolls sideways.
 */
export async function snap(page: Page, flow: string, width: number | string): Promise<void> {
  await page.waitForFunction(() => ((window as unknown as { __overlaysMoving?: number }).__overlaysMoving ?? 0) === 0);
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

/** The account's user id on this database (never a fixed number: it depends on the seed). */
export const userIdOf = (email: string): number => Number(psql(`select id from auth_user where email = '${email}'`));

/**
 * The staff record linked to the account `email`, created (named `E2E Task …`) if it has none: one live
 * record per account, so one left by another spec is reused. The account must exist: sign it in first.
 */
export async function recordOf(context: BrowserContext, email: string, label: string): Promise<{ id: string }> {
  const user = userIdOf(email);
  expect(user, `${email} has signed in once`).toBeGreaterThan(0);
  const existing = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/staff/members?user_id=${user}`);
  expect(existing.status).toBe(200);
  return existing.data.rows[0] ?? (await post<{ id: string }>(context, '/staff/members', { first_name: `${TAG} ${label}`, last_name: Date.now().toString(36), user_id: user }));
}

export async function signedIn(
  browser: Browser,
  next: string,
  credentials?: Credentials,
  viewport: { width: number; height: number } = VIEWPORTS.desktop,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  await context.addInitScript(countMovingOverlays);
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
