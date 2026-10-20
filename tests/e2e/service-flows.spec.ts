// flow: SERVICE-F01 SERVICE-F02 SERVICE-F03 SERVICE-F04 SERVICE-F05 SERVICE-F07 SERVICE-F08 SERVICE-F11 SERVICE-F12 SERVICE-F13 SERVICE-F16 SERVICE-F17 SERVICE-F18 SERVICE-F19 SERVICE-F30 SERVICE-F31 SERVICE-F32
// Every flow of Services that has a screen, end to end in each of the three sizes (apps/service/WORKBOOK.md),
// with one screenshot per flow and size (`APP-SERVICE-<flow>-<width>`), against the real Taxes, Staff,
// Customers, Schedules and Appointments: the owner of hub `a` creates and edits a category (F07), creates a
// service in it (F01), edits it (F02) and opens its price (F03), assigns a professional (F31) and changes,
// stars and removes the assignment (F32); archives it, warned of the appointment that keeps using it (F04),
// and restores it from the archived view (F05); deletes the category, told how many services it leaves
// (F08); saves the settings (F11); creates and edits a voucher (F12, F13), sees who bought it (F16), adjusts
// one purchase (F18) and voids the other (F17), reads its movements (F19) and, once a buyer's card is
// deleted in Customers, finds it among the vouchers with no customer (F30). What it creates is «E2E Svc …».
import { expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import {
  cleanUp,
  clearFilters,
  filterBy,
  FLOW_VIEWPORTS,
  named,
  noHorizontalScroll,
  ownerPage,
  pick,
  post,
  rowAction,
  settled,
} from './service-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** A Tuesday `weeks` + five weeks ahead, as `YYYY-MM-DD`: one open day of its own per size. */
function aTuesday(weeks: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + 7 * weeks + ((9 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

/** Picks `option` of the `ion-select` with `testid` (its popover). */
async function choose(page: Page, testid: string, option: string): Promise<void> {
  await page.locator(`[data-testid=${testid}]`).click();
  await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${option}\\s*$`) }).click();
  await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
}

FLOW_VIEWPORTS.forEach((vp, index) => {
  test(`Services flows at ${vp.label}: catalog, professionals, archive, categories, settings and vouchers`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/service/categories', vp);
    const capture = async (flow: string) => {
      await settled(page);
      await page.screenshot({ path: shot(`APP-SERVICE-${flow}-${vp.label}`) });
    };
    const settings = await api<{ default_duration: number }>(context, A, 'GET', '/service/settings');
    const category = named('Hair');
    const service = named('Haircut');
    const bono = named('Bono');
    try {
      const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'Stylist' });
      const lucia = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Lucía') });
      const marta = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Marta') });

      // SERVICE-F07: a category, created and then edited from its row.
      let view = shown(page);
      await view.locator('[data-testid=service-categories-empty], [data-testid=service-categories-row]').first().waitFor({ state: 'visible' });
      await view.locator('[data-testid=service-categories-add]').click();
      await page.locator('[data-testid=service-category-form-name] input').fill(category);
      await page.locator('[data-testid=service-category-form-submit]').click();
      const categoryRow = view.locator('[data-testid=service-categories-row]', { hasText: category });
      await expect(categoryRow).toBeVisible();
      await categoryRow.getByText(category).first().click();
      await expect(page.locator('ion-modal[data-testid=service-category-form] ion-title')).toHaveText(`Editing category — ${category}`);
      await page.locator('[data-testid=service-category-form-sort_order] input').fill('3');
      await capture('SERVICE-F07');
      await page.locator('[data-testid=service-category-form-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-category-form]')).toBeHidden();
      await expect.poll(() => psql(`select sort_order from service_category where name = '${category}'`)).toBe('3');

      // SERVICE-F01: «New service» in that category with Taxes' «Service — generic», the price as typed.
      await page.goto(`${A}/service/services`);
      view = shown(page);
      await view.locator('[data-testid=service-services-empty], [data-testid=service-services-row]').first().waitFor({ state: 'visible' });
      await view.locator('[data-testid=service-services-add]').click();
      await page.locator('[data-testid=service-form-name] input').fill(service);
      await page.locator('[data-testid=service-form-price] input').fill('22.5');
      await page.locator('[data-testid=service-form-duration] input').fill('30');
      await pick(page, 'service-form-category', category.split(' ').pop()!, category);
      await pick(page, 'service-form-tax', 'generic', 'Service — generic');
      await capture('SERVICE-F01');
      await page.locator('[data-testid=service-form-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-form]')).toBeHidden();
      const row = view.locator('[data-testid=service-services-row]', { hasText: service });
      await expect(row).toContainText(category);
      await expect(row).toContainText('€22.50');
      await expect(row).toContainText('Active');
      const serviceId = psql(`select id from service_service where name = '${service}'`);

      // SERVICE-F31: «Editing service» assigns the professional with their own minutes and price.
      await row.getByText(service).first().click();
      await expect(page.locator('ion-modal[data-testid=service-form] ion-title')).toHaveText(`Editing service — ${service}`);
      await expect(page.locator('[data-testid=service-professionals-empty]')).toContainText('Nobody assigned yet');
      await pick(page, 'service-professionals-member', member.full_name.split(' ')[3], member.full_name);
      // Who is being assigned and what each field asks read whole, at every size.
      const clipped = (selector: string) =>
        page.locator(selector).first().evaluate((el) => el.scrollWidth - el.clientWidth);
      expect(await clipped('[data-testid=service-professionals-member] input'), `member at ${vp.label}`).toBeLessThanOrEqual(1);
      expect(await clipped('[data-testid=service-professionals-minutes] .label-text'), `minutes at ${vp.label}`).toBeLessThanOrEqual(1);
      expect(await clipped('[data-testid=service-professionals-price] .label-text'), `price at ${vp.label}`).toBeLessThanOrEqual(1);
      await page.locator('[data-testid=service-professionals-minutes] input').fill('40');
      await page.locator('[data-testid=service-professionals-price] input').fill('25');
      await page.locator('[data-testid=service-professionals-assign]').click();
      const assignment = page.locator('[data-testid^=service-professionals-row-]');
      await expect(assignment).toContainText('40 min · €25.00');
      await assignment.scrollIntoViewIfNeeded();
      await capture('SERVICE-F31');

      // SERVICE-F32: their minutes changed and saved, made their main service, then removed.
      const assignmentId = (await assignment.getAttribute('data-testid'))!.replace('service-professionals-row-', '');
      await page.locator(`[data-testid=service-professionals-minutes-${assignmentId}] input`).fill('45');
      await page.locator(`[data-testid=service-professionals-save-${assignmentId}]`).click();
      await expect(assignment).toContainText('45 min · €25.00');
      await page.locator(`[data-testid=service-professionals-make-primary-${assignmentId}]`).click();
      await expect(page.locator(`[data-testid=service-professionals-primary-${assignmentId}]`)).toHaveText('Main service');
      await capture('SERVICE-F32');
      await page.locator(`[data-testid=service-professionals-remove-${assignmentId}]`).click();
      await expect(page.locator('[data-testid=service-professionals-empty]')).toBeVisible();
      expect(psql(`select count(*) from service_assignment where service_id = '${serviceId}'`)).toBe('0');

      // SERVICE-F02 and F03: a new price and the pricing «From», saved; the table follows on its own.
      await page.locator('[data-testid=service-form-price] input').fill('25');
      await choose(page, 'service-form-pricing_type', 'From');
      await page.locator('[data-testid=service-form-name] input').scrollIntoViewIfNeeded();
      await capture('SERVICE-F02');
      await page.locator('[data-testid=service-form-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-form]')).toBeHidden();
      await expect(row).toContainText('€25.00');
      await expect(row).toContainText('From');
      await noHorizontalScroll(page, `services ${vp.label}`);
      await capture('SERVICE-F03');

      // SERVICE-F04: an appointment of Appointments keeps using it; «Archive» says so and archives anyway.
      const day = aTuesday(index);
      await post(context, '/schedule/special_days', {
        date: day,
        name: named('Open'),
        is_closed: false,
        intervals: [{ open_time: '09:00', close_time: '18:00' }],
      });
      await post(context, '/appointment/appointments', {
        customer_id: lucia.id,
        services: [{ service_id: serviceId }],
        staff_id: member.id,
        start: `${day}T10:00`,
      });
      await rowAction(page, 'service-services', serviceId, 'archive');
      const archive = page.locator('ion-modal[data-testid=service-services-archive]');
      await expect(archive).toContainText(`${service} — it will no longer be offered or bookable.`);
      await expect(archive).toContainText('1 upcoming appointment(s) still use this service.');
      await expect(page.locator('[data-testid=service-services-archive-submit]')).toBeInViewport();
      await capture('SERVICE-F04');
      await page.locator('[data-testid=service-services-archive-submit]').click();
      await expect(archive).toBeHidden();
      await expect(row).toHaveCount(0);

      // SERVICE-F05: the archived view (behind «Filters», where each range names its column) offers only Restore.
      await shown(page).locator('[data-testid=service-services-filters-toggle]').click();
      const panel = shown(page).locator('[data-testid=service-services-filters-panel]');
      await expect(panel.locator('.data-table__drawer-label', { hasText: 'Price' })).toBeVisible();
      await expect(panel.locator('.data-table__drawer-label', { hasText: 'Duration (min)' })).toBeVisible();
      await capture('SERVICE-F05-filters');
      await panel.locator('[data-testid=service-services-filters-close]').click();
      await expect(panel).toBeHidden();
      await filterBy(page, 'service-services', 'status', 'Archived');
      await expect(row).toContainText('Archived');
      await capture('SERVICE-F05');
      await rowAction(page, 'service-services', serviceId, 'restore');
      await expect(row).toHaveCount(0);
      expect(psql(`select is_active from service_service where id = '${serviceId}'`)).toBe('t');
      await clearFilters(page, 'service-services');
      await expect(row).toContainText('Active');

      // SERVICE-F08: deleting the category says how many services it leaves without one.
      await page.goto(`${A}/service/categories`);
      view = shown(page);
      const categoryId = psql(`select id from service_category where name = '${category}'`);
      await rowAction(page, 'service-categories', categoryId, 'delete');
      const deletion = page.locator('ion-modal[data-testid=service-categories-delete]');
      await expect(deletion).toContainText('1 service(s) will be left without a category.');
      await expect(page.locator('[data-testid=service-categories-delete-submit]')).toBeInViewport();
      await capture('SERVICE-F08');
      await page.locator('[data-testid=service-categories-delete-submit]').click();
      await expect(deletion).toBeHidden();
      await expect(view.locator('[data-testid=service-categories-row]', { hasText: category })).toHaveCount(0);
      expect(psql(`select category_id is null from service_service where id = '${serviceId}'`)).toBe('t');

      // SERVICE-F11: the settings a new service takes.
      await page.goto(`${A}/service/settings`);
      await page.locator('[data-testid=service-settings-default_duration] input').fill('45');
      await page.locator('[data-testid=service-settings-save]').click();
      await expect(page.locator('[data-testid=service-settings-saved]')).toContainText('Settings saved.');
      await capture('SERVICE-F11');

      // SERVICE-F12: «New package» with Uses, Validity, a closed price and a line with the service.
      await page.goto(`${A}/service/packages`);
      view = shown(page);
      await view.locator('[data-testid=service-packages-empty], [data-testid=service-packages-row]').first().waitFor({ state: 'visible' });
      await view.locator('[data-testid=service-packages-add]').click();
      await page.locator('[data-testid=service-package-form-name] input').fill(bono);
      await page.locator('[data-testid=service-package-form-max_uses] input').fill('5');
      await page.locator('[data-testid=service-package-form-validity_days] input').fill('180');
      await page.locator('[data-testid=service-package-form-fixed_price] input').fill('90');
      await pick(page, 'service-package-form-line-service-0', service.split(' ').pop()!, service);
      // The line's service reads whole, at every size: on a phone the line stacks instead of squeezing it.
      const lineService = page.locator('[data-testid=service-package-form-line-service-0] input');
      await expect(lineService).toHaveValue(service);
      expect(await lineService.evaluate((el: HTMLInputElement) => el.scrollWidth - el.clientWidth), `line service at ${vp.label}`).toBeLessThanOrEqual(1);
      await capture('SERVICE-F12');
      await page.locator('[data-testid=service-package-form-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-package-form]')).toBeHidden();
      const packageRow = view.locator('[data-testid=service-packages-row]', { hasText: bono });
      await expect(packageRow).toContainText('€90.00');
      await expect(packageRow).toContainText('Active');
      const packageId = psql(`select id from service_package where name = '${bono}'`);

      // SERVICE-F13: editing changes its terms but never its lines.
      await packageRow.getByText(bono).first().click();
      await expect(page.locator('ion-modal[data-testid=service-package-form] ion-title')).toHaveText(`Editing package — ${bono}`);
      await expect(page.locator('[data-testid=service-package-form-lines-fixed]')).toContainText(
        'The services included cannot be changed once created',
      );
      await page.locator('[data-testid=service-package-form-validity_days] input').fill('200');
      await expect(page.locator('[data-testid=service-package-form-submit]')).toBeInViewport();
      await capture('SERVICE-F13');
      await page.locator('[data-testid=service-package-form-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-package-form]')).toBeHidden();
      await expect.poll(() => psql(`select validity_days from service_package where id = '${packageId}'`)).toBe('200');

      // SERVICE-F16: two customers bought it (granted through the API, as the assistant does), one spent a session.
      const sold = await post<{ id: string }>(context, '/service/grants', { package_id: packageId, customer_id: lucia.id, amount: 9000 });
      const untouched = await post<{ id: string }>(context, '/service/grants', { package_id: packageId, customer_id: marta.id, amount: 9000 });
      await post(context, '/service/grants/redeem', { id: sold.id, service_id: serviceId }, 200);
      await rowAction(page, 'service-packages', packageId, 'grants');
      const grants = page.locator('ion-modal[data-testid=service-grants]');
      await expect(grants.locator('[data-testid=service-grants-title]')).toContainText(`Sold vouchers — ${bono}`);
      await expect(grants.locator(`[data-testid=service-grants-row-${sold.id}]`)).toContainText('1 used · 4 left');
      await expect(grants.locator(`[data-testid=service-grants-row-${untouched.id}]`)).toContainText('0 used · 5 left');
      await capture('SERVICE-F16');

      // SERVICE-F18: one more session, with its reason and what it leaves.
      await grants.locator(`[data-testid=service-grants-adjust-${sold.id}]`).click();
      await page.locator('[data-testid=service-grant-adjust-uses] input').fill('1');
      await page.locator('[data-testid=service-grant-adjust-reason] textarea').fill('Courtesy for the delay');
      await expect(page.locator('[data-testid=service-grant-adjust-preview]')).toContainText('After the adjustment: 5 session(s) left');
      await expect(page.locator('[data-testid=service-grant-adjust-submit]')).toBeInViewport();
      await capture('SERVICE-F18');
      await page.locator('[data-testid=service-grant-adjust-submit]').click();
      await expect(grants.locator(`[data-testid=service-grants-row-${sold.id}]`)).toContainText('Given afterwards: +1 session(s), +0 day(s)');

      // SERVICE-F17: the purchase never used is voided, with its reason.
      await grants.locator(`[data-testid=service-grants-void-${untouched.id}]`).click();
      await expect(page.locator('ion-modal[data-testid=service-grant-void]')).toContainText(`The voucher of customer ${marta.name} (€90.00)`);
      await page.locator('[data-testid=service-grant-void-reason] textarea').fill('Sold to the wrong customer');
      await expect(page.locator('[data-testid=service-grant-void-submit]')).toBeInViewport();
      await capture('SERVICE-F17');
      await page.locator('[data-testid=service-grant-void-submit]').click();
      await expect(grants.locator(`[data-testid=service-grants-row-${untouched.id}]`)).toContainText('Voided by');
      await grants.locator('[data-testid=service-grants-close]').click();
      await expect(grants).toBeHidden();

      // SERVICE-F19: the courtesy and the session, the most recent first.
      await rowAction(page, 'service-packages', packageId, 'movements');
      const movements = page.locator('ion-modal[data-testid=service-movements]');
      await expect(movements.locator('[data-testid^=service-movements-row-]').first()).toContainText('Courtesy');
      await expect(movements.locator('[data-testid^=service-movements-row-]').nth(1)).toContainText('Delivered');
      await capture('SERVICE-F19');
      await movements.locator('[data-testid=service-movements-close]').click();
      await expect(movements).toBeHidden();

      // SERVICE-F30: Lucía's card deleted in Customers; her voucher shows among the ones with no customer.
      await post(context, '/customer/customers/delete', { id: lucia.id }, 200);
      await view.locator('[data-testid=service-packages-orphans-open]').click();
      const orphans = page.locator('ion-modal[data-testid=service-orphans]');
      await expect(orphans.locator(`[data-testid=service-orphans-row-${sold.id}]`)).toContainText(`Customer reference: ${lucia.id}`);
      await expect(orphans.locator(`[data-testid=service-orphans-row-${sold.id}]`)).toContainText('5 session(s) left');
      await capture('SERVICE-F30');
      await orphans.locator('[data-testid=service-orphans-close]').click();
      await expect(orphans).toBeHidden();

      // SERVICE-F13, deleting: it asks first, and the Deleted view still finds what was sold.
      await rowAction(page, 'service-packages', packageId, 'delete');
      await expect(page.locator('ion-modal[data-testid=service-packages-delete]')).toContainText('the package and its 1 line(s) leave the catalogue');
      await page.locator('[data-testid=service-packages-delete-submit]').click();
      await expect(page.locator('ion-modal[data-testid=service-packages-delete]')).toBeHidden();
      await expect(packageRow).toHaveCount(0);
      await filterBy(page, 'service-packages', 'status', 'Deleted');
      await expect(packageRow).toContainText('Deleted');
      await noHorizontalScroll(page, `packages ${vp.label}`);
    } finally {
      await api(context, A, 'POST', '/service/settings', { default_duration: settings.data.default_duration });
      await context.close();
    }
  });
});
