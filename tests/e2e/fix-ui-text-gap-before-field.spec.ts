// hub#2317, hub#2308, hub#2267, hub#2474 — a text does not touch what follows it. An outlined field raises its label over
// its top edge, and in «Erase personal data», «Health and allergies» and the window that cancels a ticket (or a
// reservation) that label lay on the last line of the text above; in Settings › Business, on a phone, the explanation of
// «Currency» touched its value. Each distance is measured between the two boxes, in English and in Spanish, on a phone, a
// tablet and a desk. The same window of Appointments, of Online booking and of the failed events is measured in
// appointment-agenda, online-booking-flow and base-system.
// flow: CUSTOMER-F16, CUSTOMER-F32, KITCHEN-F22, RESERVATION-F09, BASE-F50
import { type Browser, expect, type Page, test } from '@playwright/test';

import { cleanUp, createCard, e2eName, inputOf, spanishMobile } from './customer-helpers';
import { expectRoomOverLabel, expectTextClearOfLabel } from './field-labels';
import { A, capture, hostPage, login, psql, saveSessionForTheSweep, shown, signedInSpanish, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { presentedDialog } from './inventory-helpers';
import { bookingOn, cleanUpTagged, guestRowInTheBook, madridDay } from './reservation-helpers';
import { WINDOW_SIZES as SIZES } from './screen';
import { post, rowAction } from './service-helpers';

const DESK = SIZES[2];
const LANGS = ['en', 'es'] as const;
type Lang = (typeof LANGS)[number];

const APPS = ['tax', 'customer', 'schedule', 'inventory', 'sale', 'printing', 'kitchen', 'table', 'reservation'];
const TAG = 'E2E Gap';
const TICKET = 'e2e gap ticket';
const AHEAD = 3;
const BOOK = { day: madridDay(AHEAD), sentinel: 79, reason: `${TAG} open` };

const turnedOn: string[] = [];

function cleanAll(): void {
  const tickets = `select id from kitchen_ticket where label like '${TICKET}%'`;
  psql(
    [
      `delete from kitchen_logentry where ticket_id in (${tickets})`,
      `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
      `delete from kitchen_ticket where label like '${TICKET}%'`,
    ].join('; '),
  );
  cleanUpTagged(TAG, BOOK.sentinel);
  cleanUp();
}

test.beforeAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/' });
  await turnOnMissing(context, A, APPS, turnedOn);
  await context.close();
  cleanAll();
});

test.afterAll(async ({ browser }) => {
  cleanAll();
  const { context } = await hostPage(browser, A, { next: '/' });
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

/** The owner on `next`, with the Hub in `lang`. */
async function ownerPage(browser: Browser, lang: Lang, next: string): Promise<Page> {
  if (lang === 'es') return (await signedInSpanish(browser, DESK, next)).page;
  const context = await browser.newContext({ baseURL: A, viewport: DESK, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return page;
}

/** `check` at each size, once nothing moves, and the screen captured as `name`. */
async function atEachSize(page: Page, name: string, check: (where: string) => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await untilStill(page);
    await check(`${name} at ${size.label}`);
    await capture(page, `GAP-${name}-${size.label}`);
  }
  await page.setViewportSize(DESK);
}

for (const lang of LANGS) {
  test(`in ${lang}, «Erase personal data»: the reason's label is clear of the warning, also under a refusal`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/customer/customers');
    try {
      const card = await createCard(page.context(), { name: e2eName('Gap Erase'), phone: spanishMobile() });
      await page.goto(`/customer/customers/${card.id}`);
      await shown(page).locator('[data-testid=customer-detail-erase]').click();
      const panel = shown(page).locator('[data-testid=customer-erase]');
      const reason = panel.locator('[data-testid=customer-erase-reason]');
      await inputOf(panel, 'customer-erase-reason').fill('Asked at the counter');
      await saveSessionForTheSweep(page.context());
      await atEachSize(page, `CUSTOMER-F16-${lang}`, async (where) => {
        await panel.scrollIntoViewIfNeeded();
        await expectTextClearOfLabel(panel.locator('p'), reason, where);
      });

      await page.route('**/api/customer/customers/erase', (route) =>
        route.fulfill({ status: 409, json: { error: { code: 'customer.not_now', message: 'Not now.' } } }),
      );
      await panel.locator('[data-testid=customer-erase-submit]').click();
      const refusal = panel.locator('[data-testid=customer-erase-error]');
      await expect(refusal).toContainText('Not now.');
      await atEachSize(page, `CUSTOMER-F16-refused-${lang}`, async (where) => {
        await panel.scrollIntoViewIfNeeded();
        await expectRoomOverLabel(refusal, reason, null, where);
        const texts = await Promise.all([panel.locator('p'), refusal].map((text) => text.boundingBox()));
        expect(texts[1]!.y - (texts[0]!.y + texts[0]!.height), `${where}: the warning and the refusal`).toBeGreaterThanOrEqual(8);
      });
    } finally {
      await page.context().close();
    }
  });

  test(`in ${lang}, «Health and allergies»: the first label is clear of who gave the permission and when`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/customer/customers');
    try {
      const card = await createCard(page.context(), { name: e2eName('Gap Health') });
      await page.goto(`/customer/customers/${card.id}`);
      const health = shown(page).locator('[data-testid=customer-health]');
      await health.locator('[data-testid=customer-health-ask]').click();
      await health.locator('[data-testid=customer-health-confirm]').click();
      await health.locator('[data-testid=customer-health-edit]').click();
      const allergies = health.locator('[data-testid=customer-health-allergies-input]');
      await allergies.locator('textarea').fill('PPD');
      await atEachSize(page, `CUSTOMER-F32-${lang}`, async (where) => {
        await health.scrollIntoViewIfNeeded();
        const permission = health.locator('[data-testid=customer-health-consent]');
        await expectTextClearOfLabel(permission, allergies, where);
        await expectRoomOverLabel(permission, allergies, health.locator('[data-testid=customer-health-date-input]'), where);
      });
    } finally {
      await page.context().close();
    }
  });

  test(`in ${lang}, cancelling a ticket: the reason's label is clear of the warning`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/kitchen/tickets');
    try {
      const ticket = await post<{ id: string }>(page.context(), '/kitchen/tickets', { label: `${TICKET} ${lang}`, items: [{ name: 'Dish', quantity: '1' }] });
      await page.reload();
      await shown(page).locator('[data-testid=kitchen-tickets-search] input').fill(`${TICKET} ${lang}`);
      const dialog = await presentedDialog(page, 'kitchen-tickets-cancel', () => rowAction(page, 'kitchen-tickets', ticket.id, 'cancel'));
      const reason = dialog.locator('[data-testid=kitchen-tickets-cancel-reason]');
      await reason.locator('input').fill('Guest left');
      await atEachSize(page, `KITCHEN-F22-${lang}`, (where) => expectTextClearOfLabel(dialog.locator('p'), reason, where));
    } finally {
      await page.context().close();
    }
  });

  test(`in ${lang}, cancelling a reservation: the reason's label is clear of the warning`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/reservation/reservations');
    try {
      const guest = `${TAG} Eva ${lang}`;
      const id = await bookingOn(BOOK)(page.context(), guest);
      await expect(await guestRowInTheBook(page, { ahead: AHEAD, day: BOOK.day }, guest)).toBeVisible();
      const dialog = await presentedDialog(page, 'reservation-step-cancel', () => rowAction(page, 'reservation-list', id, 'cancel'));
      const reason = dialog.locator('[data-testid=reservation-step-cancel-reason]');
      await reason.locator('textarea').fill('Plans changed');
      await atEachSize(page, `RESERVATION-F09-${lang}`, (where) => expectTextClearOfLabel(dialog.locator('p'), reason, where));
    } finally {
      await page.context().close();
    }
  });

  test(`in ${lang}, Settings › Business: the explanation of a row is clear of its value`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/settings#business');
    try {
      const rows = shown(page).locator('ion-item', { has: page.locator('[data-testid=settings-row-value]') });
      await expect(shown(page).locator('[data-testid=business-currency] [data-testid=settings-row-value]')).toHaveText('EUR · Euro');
      await atEachSize(page, `BASE-F50-${lang}`, async (where) => {
        const gaps = await rows.evaluateAll((items) =>
          items.map((item) => {
            const text = item.querySelector('ion-label')!.getBoundingClientRect();
            const value = item.querySelector('[data-testid=settings-row-value]')!.getBoundingClientRect();
            return Math.round(value.left - text.right);
          }),
        );
        expect(gaps, `${where}: the rows with a value`).toHaveLength(5);
        expect(Math.min(...gaps), `${where}: between the text and the value`).toBeGreaterThanOrEqual(8);
      });
    } finally {
      await page.context().close();
    }
  });
}
