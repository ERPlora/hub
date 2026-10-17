// Services → Categories and Services in Chrome (WORKBOOK SERVICE-F01 to F08, F31, F32), with the real
// Taxes and Staff apps: the owner creates a category (a repeated name is refused under Name), a service
// in it with Taxes' «Service — generic» and a price typed as a person does, assigns a professional of
// Staff with their own minutes and price in «Editing service», archives the service (asking first),
// finds it under the Archived filter and restores it. Each screen is captured in three viewports.
// Everything this spec creates is named «E2E Svc …» and removed before and after it.
import { expect, test } from '@playwright/test';

import { A, psql, shot, shown } from './helpers';
import { cleanUp, named, ownerPage, pick, post, rowAction, VIEWPORTS } from './service-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('Categories and services: create, a duplicate refused, a professional assigned, archive and restore', async ({ browser }) => {
  const category = named('Hair');
  const service = named('Haircut');
  const { context, page } = await ownerPage(browser, '/service/categories');
  try {
    const professional = await post<{ id: string; full_name: string }>(context, '/staff/members', {
      first_name: `${named('Ana')}`,
      last_name: 'Stylist',
    });

    // Categories: create one; the same name in another case is refused under Name (409).
    let view = shown(page);
    await view.locator('[data-testid=service-categories-empty], [data-testid=service-categories-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=service-categories-add]').click();
    await page.locator('[data-testid=service-category-form-name] input').fill(category);
    await page.locator('[data-testid=service-category-form-submit]').click();
    await expect(view.locator('[data-testid=service-categories-row]', { hasText: category })).toBeVisible();
    await view.locator('[data-testid=service-categories-add]').click();
    await page.locator('[data-testid=service-category-form-name] input').fill(category.toUpperCase());
    await page.locator('[data-testid=service-category-form-submit]').click();
    await expect(page.locator('[data-testid=service-category-form-error]')).toContainText(
      'There is already a category with that name. Pick another name.',
    );
    await page.screenshot({ path: shot('service-categories-409') });
    await page.locator('[data-testid=service-category-form-cancel]').click();

    // Services: «New service» with the category and Taxes' factory category, the price as typed.
    await page.goto(`${A}/service/services`);
    view = shown(page);
    await view.locator('[data-testid=service-services-empty], [data-testid=service-services-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=service-services-add]').click();
    await page.locator('[data-testid=service-form-name] input').fill(service);
    await page.locator('[data-testid=service-form-price] input').fill('22.5');
    await page.locator('[data-testid=service-form-duration] input').fill('30');
    await pick(page, 'service-form-category', category.split(' ').pop()!, category);
    await pick(page, 'service-form-tax', 'generic', 'Service — generic');
    await page.screenshot({ path: shot('service-services-new') });
    await page.locator('[data-testid=service-form-submit]').click();
    const row = view.locator('[data-testid=service-services-row]', { hasText: service });
    await expect(row).toContainText(category);
    await expect(row).toContainText('€22.50');
    await expect(row).toContainText('Active');

    // «Editing service»: assign the professional with their own minutes and price.
    await row.getByText(service).click();
    await expect(page.locator('ion-modal[data-testid=service-form] ion-title')).toHaveText(`Editing service — ${service}`);
    await expect(page.locator('[data-testid=service-professionals-empty]')).toContainText('Nobody assigned yet');
    await pick(page, 'service-professionals-member', professional.full_name.split(' ')[3], professional.full_name);
    await page.locator('[data-testid=service-professionals-minutes] input').fill('40');
    await page.locator('[data-testid=service-professionals-price] input').fill('25');
    await page.locator('[data-testid=service-professionals-assign]').click();
    await expect(page.locator('[data-testid^=service-professionals-row-]')).toContainText('40 min · €25.00');
    await page.screenshot({ path: shot('service-services-edit') });
    await page.locator('[data-testid=service-form-cancel]').click();

    // Archive asks first; the archived view offers Restore.
    const serviceId = psql(`select id from service_service where name = '${service}'`);
    await rowAction(page, 'service-services', serviceId, 'archive');
    await expect(page.locator('ion-modal[data-testid=service-services-archive]')).toContainText(
      `${service} — it will no longer be offered or bookable.`,
    );
    await page.locator('[data-testid=service-services-archive-submit]').click();
    await expect(page.locator('ion-modal[data-testid=service-services-archive]')).toBeHidden();
    await expect(row).toHaveCount(0);
    await view.locator('[data-testid=service-services-filter-status]').click();
    await page.locator('ion-popover').getByText('Archived', { exact: true }).click();
    await expect(row).toContainText('Archived');
    await rowAction(page, 'service-services', serviceId, 'restore');
    await expect(row).toHaveCount(0);
    expect(psql(`select is_active from service_service where id = '${serviceId}'`)).toBe('t');
    await view.locator('[data-testid=service-services-filters-clear]').click();
    await expect(row).toContainText('Active');
    await page.screenshot({ path: shot('service-services-desktop') });
  } finally {
    await context.close();
  }

  // The same screens on a tablet and on a phone (cards).
  for (const [name, viewport] of Object.entries(VIEWPORTS).filter(([key]) => key !== 'desktop')) {
    const { context: small, page: phone } = await ownerPage(browser, '/service/services', viewport);
    try {
      const view = shown(phone);
      await expect(view.getByText(service).first()).toBeVisible();
      await phone.screenshot({ path: shot(`service-services-${name}`) });
      await phone.goto(`${A}/service/categories`);
      await expect(shown(phone).getByText(category).first()).toBeVisible();
      await phone.screenshot({ path: shot(`service-categories-${name}`) });
    } finally {
      await small.close();
    }
  }
});
