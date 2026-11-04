// flow: base-money-thousands-grouping (hub#692; hub#512, hub#632, hub#656): CUSTOMER-F03, F23, F31; APPOINTMENT-F01;
// MODIFIER-F04; ONLINE_BOOKING-F01
// Customers, Appointments and Modifiers write an amount with the platform's `formatMoney` (`@erplora/ui/components`), its
// thousands grouped from four figures on: «1.234,56 €» and «€1,234.56», never «1234,56 €» (the Spanish CLDR only groups
// from five). The owner of `a`, a business in Spain, reads them in English and in Spanish at 375, 820 and 1440: the
// «Revenue» above the list, on one line (`…-customer-stats-<language>-<width>`), a card's «Spent» in the list
// (`…-customer-list-…`), its «Spent» on the card (`…-customer-facts-…`) and a purchase (`…-customer-card-…`), a service's
// price (`…-appointment-option-…`) and the total (`…-appointment-…`) in «New appointment», a service's price in the
// preview of the booking page (`…-online-booking-…`), and a supplement in the group's sheet (`…-modifier-…`). «Revenue»
// also stays on one line in the millions on a phone (`…-customer-stats-millions-375`). What the run creates is deleted
// after it, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Card, cleanUp as cleanCustomers, createCard, customersReady, e2eName, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { A, api, capture, hostPage, login, psql, shown } from './helpers';
import { dialog } from './inventory-helpers';
import { noHorizontalScroll, post } from './service-helpers';

const KEY = 'base-money-grouping';
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const DESK = SIZES[2];
const TAG = 'E2E MNYG';
const RUN = Date.now().toString(36);
/** 1.234,56 € in its minor unit, as the server keeps every amount. */
const AMOUNT = 123456;
const UNGROUPED = /1234[.,]56/;
/** 1.234.567,89 €: a business's whole revenue, the widest figure the cards above the list are expected to hold. */
const MILLIONS = 123456789;

const LANGUAGES = [
  {
    code: 'en',
    locale: 'en-US',
    amount: /€1,234\.56/,
    supplement: /\+€1,234\.56/,
    revenue: /€\d{1,3}(,\d{3})+\.\d{2}/,
  },
  {
    code: 'es',
    locale: 'es-ES',
    amount: /1\.234,56\s€/,
    supplement: /\+1\.234,56\s€/,
    revenue: /\d\.\d{3},\d{2}\s€/,
  },
] as const;

let card: Card;
let service: { id: string; name: string };
let groupId = '';
/** The settings of the booking page, put back at the end: the preview answers only while the page is on. */
let savedPage: Record<string, unknown> | null = null;
/** What the page's settings read of Appointments: written there, not here. */
const NOT_OF_THE_PAGE = ['timezone', 'min_booking_notice', 'max_advance_booking', 'slot_interval', 'auto_confirm_online', 'allow_customer_cancellation', 'cancellation_notice_hours'];

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanOwn(): void {
  const groups = `select id from modifier_modifiergroup where name like '${TAG}%'`;
  const services = `select id from service_service where name like '${TAG}%'`;
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      `delete from modifier_modifiergroup where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name like '${TAG}%'`,
    ].join('; '),
  );
}

/** The owner of `a` reading the Hub in `language`: its language cookie, as the sign-in sets it from the account. */
async function ownerIn(
  browser: Browser,
  language: (typeof LANGUAGES)[number],
  next: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: DESK.width, height: DESK.height }, locale: language.locale });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: language.code, domain: new URL(A).hostname, path: '/' }]);
  await page.goto('about:blank');
  await page.goto(`${A}${next}`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language.code}`));
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: `${process.env.E2E_SAVE_STORAGE_STATE}-${language.code}.json` });
  return { context, page };
}

const atSize = (language: (typeof LANGUAGES)[number], size: (typeof SIZES)[number]): string => `${language.code}-${size.label}`;

/** The revenue figure of the cards above the customer list. */
const revenueFigure = (page: Page): Locator => shown(page).locator('[data-testid=customer-stats-revenue] .customer-kpi__value');

/** A card's figure takes one line and all of it is inside its card: «1.234,56» over a lone «€» is what this rules out. */
async function onOneLine(figure: Locator, where: string): Promise<void> {
  const box = await figure.evaluate((element) => ({
    height: element.getBoundingClientRect().height,
    line: Number.parseFloat(getComputedStyle(element).lineHeight),
    overflow: element.scrollWidth - element.clientWidth,
  }));
  expect(box.height, `${where}: the figure wraps`).toBeLessThan(box.line * 1.5);
  expect(box.overflow, `${where}: the figure runs out of its card`).toBeLessThanOrEqual(0);
}

/** On a phone the cards go two by two, so that the table is still seen below them (CUSTOMER-F31). */
async function twoOnARow(page: Page, where: string): Promise<void> {
  const top = async (id: string): Promise<number | undefined> => (await shown(page).locator(`[data-testid=customer-stats-${id}]`).boundingBox())?.y;
  const tops = [await top('total'), await top('active'), await top('vip'), await top('revenue')];
  expect(tops[0], `${where}: «Customers» and «Active» share a row`).toBe(tops[1]);
  expect(tops[2], `${where}: «VIP» and «Revenue» share a row`).toBe(tops[3]);
}

test.beforeAll(async ({ browser }) => {
  cleanOwn();
  cleanCustomers();
  const owner = await hostPage(browser, A, { next: '/customer/customers' });
  card = await createCard(owner.context, { name: e2eName(`${TAG} Ana ${RUN}`), phone: spanishMobile() });
  // Sales reach a card through the sale app's notices (the relay): its figures and purchase are set up here.
  psql(`update customer_customer set total_purchases = 1, total_spent = ${AMOUNT}, last_purchase_at = now() where id = '${card.id}'`);
  psql(
    `insert into customer_purchase (id, customer_id, sale_id, refund_id, amount, currency, status, recorded_at, void_reason) values ` +
      `(gen_random_uuid(), '${card.id}', gen_random_uuid(), null, ${AMOUNT}, 'EUR', 'confirmed', now(), '')`,
  );
  service = await post<{ id: string; name: string }>(owner.context, '/service/services', {
    name: `${TAG} Keratin ${RUN}`,
    price: AMOUNT,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const group = await post<{ id: string }>(owner.context, '/modifier/groups', { name: `${TAG} Extras ${RUN}`, max_choices: 3 });
  groupId = group.id;
  await post(owner.context, '/modifier/options', { group_id: groupId, name: 'Cheese', price_delta: AMOUNT });
  const page = await api<Record<string, unknown>>(owner.context, A, 'GET', '/online_booking/settings');
  expect(page.status).toBe(200);
  savedPage = Object.fromEntries(Object.entries(page.data).filter(([key]) => !NOT_OF_THE_PAGE.includes(key)));
  await post(owner.context, '/online_booking/settings', { is_enabled: true }, 200);
  await owner.context.close();
});

test.afterAll(async ({ browser }) => {
  try {
    if (savedPage) {
      const owner = await hostPage(browser, A, { next: '/online_booking/bookings' });
      await post(owner.context, '/online_booking/settings', savedPage, 200);
      await owner.context.close();
    }
  } finally {
    try {
      cleanOwn();
    } finally {
      cleanCustomers();
    }
  }
});

for (const language of LANGUAGES) {
  test(`${KEY}: Customers groups the thousands of «Spent», «Revenue» and a purchase in ${language.code}`, async ({ browser }) => {
    const { context, page } = await ownerIn(browser, language, '/customer/customers');
    try {
      for (const size of SIZES) {
        const where = atSize(language, size);
        await page.setViewportSize({ width: size.width, height: size.height });
        await page.goto(`${A}/customer/customers`);
        await customersReady(page);
        await searchList(page, 'customer-list', RUN);
        const spent = rowNamed(page, 'customer-list', card.name).locator('[data-testid=customer-list-spent]');
        await expect(spent, where).toHaveText(language.amount);
        await expect(spent, where).not.toHaveText(UNGROUPED);
        await expect(revenueFigure(page), where).toHaveText(language.revenue);
        await onOneLine(revenueFigure(page), where);
        if (size === SIZES[0]) await twoOnARow(page, where);
        await noHorizontalScroll(page, where);
        await capture(page, `${KEY}-customer-stats-${where}`);
        await spent.scrollIntoViewIfNeeded();
        await capture(page, `${KEY}-customer-list-${where}`);

        await page.goto(`${A}/customer/customers/${card.id}`);
        const facts = shown(page).locator('[data-testid=customer-facts]');
        await expect(facts, where).toContainText(language.amount);
        await expect(facts, where).not.toContainText(UNGROUPED);
        await facts.getByText(language.amount).scrollIntoViewIfNeeded();
        await capture(page, `${KEY}-customer-facts-${where}`);
        const purchase = shown(page).locator('[data-testid=customer-purchase]').first().locator('.customer-purchases__amount');
        await expect(purchase, where).toHaveText(language.amount);
        await purchase.scrollIntoViewIfNeeded();
        await noHorizontalScroll(page, where);
        await capture(page, `${KEY}-customer-card-${where}`);
      }
    } finally {
      await context.close();
    }
  });

  test(`${KEY}: «New appointment» groups the thousands of a price and of the total in ${language.code}`, async ({ browser }) => {
    const { context, page } = await ownerIn(browser, language, '/appointment/agenda');
    try {
      for (const size of SIZES) {
        const where = atSize(language, size);
        await page.setViewportSize({ width: size.width, height: size.height });
        await page.goto(`${A}/appointment/agenda`);
        const view = shown(page);
        await view.locator('[data-testid=appointment-list-empty], [data-testid=appointment-list-row]').first().waitFor({ state: 'visible' });
        await view.locator('[data-testid=appointment-list-add]').click();
        const form = dialog(page, 'appointment-form');
        await expect(form).toBeVisible();

        const search = form.locator('[data-testid=appointment-form-service-add] input');
        await search.click();
        await search.fill(RUN);
        const options = page.locator('[data-testid^=appointment-form-service-add-option-]');
        const option = options.filter({ hasText: service.name }).first();
        await expect(option, where).toContainText(language.amount);
        await expect(option, where).not.toContainText(UNGROUPED);
        await capture(page, `${KEY}-appointment-option-${where}`);
        await option.click();
        await expect(options).toHaveCount(0);

        const total: Locator = form.locator('[data-testid=appointment-form-total]');
        await expect(total, where).toContainText(language.amount);
        await expect(total, where).not.toContainText(UNGROUPED);
        await total.scrollIntoViewIfNeeded();
        await noHorizontalScroll(page, where);
        await capture(page, `${KEY}-appointment-${where}`);

        await form.locator('[data-testid=appointment-form-cancel]').click();
        await expect(form).toBeHidden();
      }
    } finally {
      await context.close();
    }
  });

  test(`${KEY}: the group's sheet groups the thousands of a supplement in ${language.code}`, async ({ browser }) => {
    const { context, page } = await ownerIn(browser, language, '/modifier/groups');
    try {
      const view = shown(page);
      await view.locator('[data-testid=modifier-groups-row], [data-testid=modifier-groups-empty]').first().waitFor({ state: 'visible' });
      await view.locator('[data-testid=modifier-groups-search] input').fill(RUN);
      await view.locator(`[data-testid=modifier-groups-row][data-id="${groupId}"]`).locator('[role=cell]').first().click();
      const sheet = dialog(page, 'modifier-sheet');
      await expect(sheet).toBeVisible();
      const cheese = sheet.locator('[data-testid^=modifier-sheet-options-row-]').filter({ hasText: 'Cheese' });
      for (const size of SIZES) {
        const where = atSize(language, size);
        await page.setViewportSize({ width: size.width, height: size.height });
        await expect(cheese, where).toContainText(language.supplement);
        await expect(cheese, where).not.toContainText(UNGROUPED);
        await noHorizontalScroll(page, where);
        await capture(page, `${KEY}-modifier-${where}`);
      }
    } finally {
      await context.close();
    }
  });

  test(`${KEY}: the preview of the booking page groups the thousands of a service's price in ${language.code}`, async ({ browser }) => {
    const { context, page } = await ownerIn(browser, language, '/online_booking/preview');
    try {
      for (const size of SIZES) {
        const where = atSize(language, size);
        await page.setViewportSize({ width: size.width, height: size.height });
        await page.goto(`${A}/online_booking/preview`);
        const price = shown(page).locator(`[data-testid=ob-preview-service-${service.id}]`);
        await expect(price, where).toContainText(language.amount);
        await expect(price, where).not.toContainText(UNGROUPED);
        await price.scrollIntoViewIfNeeded();
        await noHorizontalScroll(page, where);
        await capture(page, `${KEY}-online-booking-${where}`);
      }
    } finally {
      await context.close();
    }
  });
}

test(`${KEY}: «Revenue» stays on one line in the millions on a phone`, async ({ browser }) => {
  const language = LANGUAGES[1];
  const { context, page } = await ownerIn(browser, language, '/customer/customers');
  try {
    psql(`update customer_customer set total_spent = ${MILLIONS} where id = '${card.id}'`);
    await page.setViewportSize({ width: SIZES[0].width, height: SIZES[0].height });
    await page.goto(`${A}/customer/customers`);
    await customersReady(page);
    await expect(revenueFigure(page)).toHaveText(/1\.234\.\d{3},\d{2}\s€/);
    await onOneLine(revenueFigure(page), 'millions at 375');
    await noHorizontalScroll(page, 'millions at 375');
    await capture(page, `${KEY}-customer-stats-millions-375`);
  } finally {
    await context.close();
  }
});
