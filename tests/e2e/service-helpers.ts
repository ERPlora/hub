// Shared steps of the service e2e (service-*.spec.ts): an owner's page in English, the apps' APIs for
// setup and server-side evidence (never the check itself), a Combo pick, a row action (a button, or
// inside «⋮» when the row folds them: the one every spec of the e2e takes, hub#1302), a column filter through the
// table's «Filters» panel and the cleanup every spec runs before and after it: what a run creates is named
// «E2E Svc …» and deleted from the hub's database, the appointments of its customers included.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, shown } from './helpers';

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

/** The three sizes every flow with a screen is walked and captured at. */
export const FLOW_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** Waits until nothing moves and the page is painted: helpers.ts's, the one every spec takes. */
export { settled } from './helpers';

/** The page does not scroll sideways: everything fits its width. */
export async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

/** `name` captured at each of `sizes` once `ready` has set the page there, with nothing scrolling sideways; back to
 *  1280×860 after. */
export async function capturedAtSizes(
  page: Page,
  name: string,
  sizes: readonly { label: string; width: number; height: number }[],
  ready: (viewport: { label: string; width: number; height: number }) => Promise<void>,
): Promise<void> {
  for (const viewport of sizes) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(viewport);
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    await capture(page, `${name}-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

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

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`; its list closes. */
export async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  await input.click();
  await input.fill(query);
  await page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first().click();
  await expect(page.locator(`[data-testid^=${testid}-option-]`)).toHaveCount(0);
}

/**
 * Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. The table folds them by
 * measuring its box, a frame or more after a resize or new rows (`DataTable`), so what the row showed a moment ago
 * is not what the click finds: the click goes to whichever of the two the row shows when it lands, and the entry is
 * looked for in «⋮» only when that is where it landed. Deciding first and clicking after waited for an «Edit» the table
 * had folded meanwhile until the test's time ran out (hub#1279; service-helpers.spec.ts). It is the one every spec of the
 * e2e takes, with its table's hook prefix (`inventory-products`, `tax-rules`, `members`…): nineteen copies of the old
 * one hung the same way, and row-action.test.ts keeps a second one from coming back (hub#1302).
 */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const hook = `${table}-row-${id}-${action}`;
  const menuHook = `${table}-row-${id}-menu`;
  const landed = await clickLanding(page, shown(page).locator(`[data-testid=${hook}]`).or(shown(page).locator(`[data-testid=${menuHook}]`)).first());
  if (landed === hook) return;
  if (landed !== menuHook) throw new Error(`rowAction ${hook}: the click landed on ${landed ?? 'nothing'}, neither the button nor «⋮»`);
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

/** Clicks `target` and says the `data-testid` of what the click landed on. A locator that matches either of two things
 *  (`a.or(b)`) is resolved again on each try, so the answer is what was there when the click went through: a click
 *  Playwright held back, because something else was under the pointer, never reaches the page's listeners. */
async function clickLanding(page: Page, target: Locator): Promise<string | null> {
  type Landing = Window & { e2eClickLanding?: string | null };
  await page.evaluate(() => {
    const record = (event: Event) => {
      (window as Landing).e2eClickLanding = (event.target as Element | null)?.closest('[data-testid]')?.getAttribute('data-testid') ?? null;
    };
    (window as Landing).e2eClickLanding = undefined;
    document.addEventListener('click', record, { capture: true, once: true });
  });
  await target.click();
  return page.evaluate(() => (window as Landing).e2eClickLanding ?? null);
}

/** Picks `option` in the column filter `filter` of `table`, through its «Filters» panel, and applies it. */
export async function filterBy(page: Page, table: string, filter: string, option: string): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-filters-toggle]`).click();
  const panel = shown(page).locator(`[data-testid=${table}-filters-panel]`);
  await expect(panel).toBeVisible();
  await panel.locator(`[data-testid=${table}-filter-${filter}]`).click();
  await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${option}\\s*$`) }).click();
  await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
  await panel.locator(`[data-testid=${table}-filters-apply]`).click();
  await expect(panel).toBeHidden();
}

/** Lifts every column filter of `table` from its «Filters» panel. */
export async function clearFilters(page: Page, table: string): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-filters-toggle]`).click();
  const panel = shown(page).locator(`[data-testid=${table}-filters-panel]`);
  await panel.locator(`[data-testid=${table}-filters-clear]`).click();
  await expect(shown(page).locator(`[data-testid=${table}-filters-count]`)).toHaveCount(0);
  await panel.locator(`[data-testid=${table}-filters-close]`).click();
  await expect(panel).toBeHidden();
}

/** Deletes everything a service spec created, its customers, professionals and appointments included. */
export function cleanUp(): void {
  const packages = `select id from service_package where name like '${TAG}%'`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const grants = `select id from service_grant where package_id in (${packages})`;
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  psql(
    [
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      // Sales' copy of a session spent outside the checkout (SERVICE-F21) would keep counting in a production.
      `delete from sale_vouchersession where session_id in (select id from service_redemption where grant_id in (${grants}))`,
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

/** The customer `customerId` deleted in Customers: her voucher `voucherId` shows among the ones with no customer, with
 *  her reference and its 5 sessions left. That sheet, open. */
export async function voucherWithNoCustomer(page: Page, context: BrowserContext, customerId: string, voucherId: string): Promise<Locator> {
  await post(context, '/customer/customers/delete', { id: customerId }, 200);
  await shown(page).locator('[data-testid=service-packages-orphans-open]').click();
  const orphans = page.locator('ion-modal[data-testid=service-orphans]');
  await expect(orphans.locator(`[data-testid=service-orphans-row-${voucherId}]`)).toContainText(`Customer reference: ${customerId}`);
  await expect(orphans.locator(`[data-testid=service-orphans-row-${voucherId}]`)).toContainText('5 sessions left');
  return orphans;
}
