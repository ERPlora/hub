// Shared steps of the service e2e (service-*.spec.ts): an owner's page in English, the apps' APIs for
// setup and server-side evidence (never the check itself), a Combo pick, a row action (a button, or
// inside «⋮» when the row folds them) and the cleanup every spec runs before and after it: what a run
// creates is named «E2E Svc …» and deleted from the hub's database (phase 1: hubs `a` and `b` share it).
import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';

/** Every name a service spec gives starts like this. */
export const TAG = 'E2E Svc';

/** `E2E Svc <label> <base36 time>`: unique per run. */
export const named = (label: string): string => `${TAG} ${label} ${Date.now().toString(36)}`;

/** The three viewports the screens are checked and captured in. */
export const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 820, height: 1180 },
  phone: { width: 390, height: 844 },
} as const;

export async function ownerPage(browser: Browser, next: string, viewport: { width: number; height: number } = VIEWPORTS.desktop) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
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

/** Deletes everything a service spec created, its customers and professionals included. */
export function cleanUp(): void {
  const packages = `select id from service_package where name like '${TAG}%'`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const grants = `select id from service_grant where package_id in (${packages})`;
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  psql(
    [
      `delete from service_redemption where grant_id in (${grants})`,
      `delete from service_grantadjustment where grant_id in (${grants})`,
      `delete from service_grant where package_id in (${packages}) or customer_id in (${customers})`,
      `delete from service_packageitem where package_id in (${packages}) or service_id in (${services})`,
      `delete from service_package where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name like '${TAG}%'`,
      `update service_category set parent_id = null where parent_id in (select id from service_category where name like '${TAG}%')`,
      `delete from service_category where name like '${TAG}%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}
