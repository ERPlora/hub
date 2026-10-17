// The four sections of Customers in Ioan's Chrome (WORKBOOK «Pantallas»): the footer tabs Customers,
// Groups, Tags and Fields move between them (the address follows, Back leaves the section); a row
// opens the card and its Back returns; every page at 390×844 (phone), 834×1194 (tablet) and
// 1440×900 (desktop) without horizontal scroll, with a screenshot of each for the comparison with the
// product's screens. On the phone the list shows cards and the side menu is a closed drawer. The list
// filters behind the table's funnel, with its count, at every width.
import { expect, type Page, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { A, login, record, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as
      | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })
      | null;
    const inner = content?.getScrollElement ? await content.getScrollElement() : null;
    const page = document.documentElement.scrollWidth - window.innerWidth;
    const own = inner ? inner.scrollWidth - inner.clientWidth : 0;
    return Math.max(page, own);
  });
}

test('the footer tabs move between Customers, Groups, Tags and Fields; a row opens the card and Back returns', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Navigation'), phone: spanishMobile() });
  await customersReady(page);
  for (const [tab, path, ready] of [
    ['groups', '/customer/groups', 'customer-groups'],
    ['tags', '/customer/tags', 'customer-tags'],
    ['fields', '/customer/fields', 'customer-fields'],
    ['customers', '/customer/customers', 'customer-list'],
  ] as const) {
    await shown(page).locator(`[data-testid=tab-${tab}]`).click();
    await page.waitForURL(new RegExp(`${path}$`));
    await expect(shown(page).locator(`[data-testid=${ready}-search]`)).toBeVisible();
    await expect(shown(page).locator(`[data-testid=tab-${tab}]`)).toHaveClass(/segment-button-checked/);
  }
  await searchList(page, 'customer-list', card.name);
  await rowNamed(page, 'customer-list', card.name).click();
  await page.waitForURL(new RegExp(`/customer/customers/${card.id}$`));
  await expect(shown(page).locator('[data-testid=customer-facts]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=tab-customers]')).toHaveClass(/segment-button-checked/);
  await shown(page).locator('[data-testid=topbar-back]').click();
  await page.waitForURL(/\/customer\/customers$/);
});

test('every page at 390 / 834 / 1440 without horizontal scroll; the phone shows cards', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, {
    name: e2eName('Viewport customer with a fairly long name to test wrapping'),
    phone: spanishMobile(),
    email: 'viewport.e2e@example.com',
    tax_id: '12345678Z',
    company_name: 'ACME Peluqueros S.L.',
    address: 'Calle Mayor 1',
    city: 'Madrid',
    postal_code: '28001',
    country: 'ES',
  });
  const results: Record<string, Record<string, number>> = {};
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    results[vp.label] = {};
    for (const [name, path, ready] of [
      ['customers', '/customer/customers', ['[data-testid=customer-stats-total][data-value]', '[data-testid=customer-list-row], [data-testid=customer-list-empty]']],
      ['card', `/customer/customers/${card.id}`, ['[data-testid=customer-facts]', '[data-testid^=customer-groups-item-], [data-testid=customer-groups-empty]', '[data-testid=customer-activity-item], [data-testid=customer-activity-empty]']],
      ['groups', '/customer/groups', ['[data-testid=customer-groups-row], [data-testid=customer-groups-empty]']],
      ['tags', '/customer/tags', ['[data-testid=customer-tags-row], [data-testid=customer-tags-empty]']],
      ['fields', '/customer/fields', ['[data-testid=customer-fields-row], [data-testid=customer-fields-empty]']],
    ] as const) {
      await page.goto(path);
      // Every block of the page painted its data (or its empty state), not just its frame.
      for (const selector of ready) await shown(page).locator(selector).first().waitFor({ state: 'visible' });
      await expect.poll(() => horizontalOverflow(page), `${name} at ${vp.label}`).toBeLessThanOrEqual(1);
      results[vp.label][name] = await horizontalOverflow(page);
      await page.screenshot({ path: shot(`customer-${name}-${vp.label}`), fullPage: false });
    }
    if (vp.label === '390') {
      await page.goto('/customer/customers');
      await customersReady(page);
      await expect(shown(page).locator('.data-table__cards')).toBeVisible();
      // The phone has the whole width: the side menu is a closed drawer (PLAN-MIGRATIONS §16).
      await expect(page.locator('ion-split-pane')).not.toHaveClass(/split-pane-visible/);
      await expect(page.locator('ion-menu.dash-menu')).toBeHidden();
    }
  }
  record('customer-viewports', results);
});

// flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
test('FIX-DATATABLE-HUB-FILTERS-1: Customers filter by Stage behind the funnel, with its count, the panel open at every width', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const stamp = `FIL${Date.now().toString(36)}`;
  const vip = await createCard(context, { name: e2eName(`${stamp} vip`), phone: spanishMobile(), lifecycle_stage: 'vip' });
  const lead = await createCard(context, { name: e2eName(`${stamp} lead`), phone: spanishMobile() });
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/customer/customers');
    await customersReady(page);
    await searchList(page, 'customer-list', stamp);
    await expect(rowNamed(page, 'customer-list', lead.name)).toBeVisible();
    const panel = shown(page).locator('[data-testid=customer-list-filters-panel]');
    const toggle = shown(page).locator('[data-testid=customer-list-filters-toggle]');
    await toggle.click();
    await expect(panel).toBeVisible();
    await panel.locator('[data-testid=customer-list-filter-lifecycle_stage]').click();
    const popover = page.locator('ion-popover.select-popover');
    await popover.locator('ion-radio').filter({ hasText: /^\s*VIP\s*$/ }).click();
    await expect(popover).toHaveCount(0);
    await panel.locator('[data-testid=customer-list-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(shown(page).locator('[data-testid=customer-list-filters-count]')).toHaveText('1');
    await expect(rowNamed(page, 'customer-list', vip.name)).toBeVisible();
    await expect(rowNamed(page, 'customer-list', lead.name)).toHaveCount(0);
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-1-customer-${vp.label}`) });
    await panel.locator('[data-testid=customer-list-filters-clear]').click();
    await expect(shown(page).locator('[data-testid=customer-list-filters-count]')).toHaveCount(0);
    await panel.locator('[data-testid=customer-list-filters-close]').click();
    await expect(panel).toBeHidden();
  }
});
