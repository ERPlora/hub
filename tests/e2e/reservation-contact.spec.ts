// flow: RESERVATION-F06, RESERVATION-F08, RESERVATION-F14 — a guest's phone and email reach only whoever sees the
// customers' contact details (BASE-F119). The employee holds that permission (base/apps.py), so they still see the book
// and the waitlist with «Phone» and the booking panel with the guest's phone, at every width; nobody sorts them by the
// phone any more (the API answers 422), and a filter by it is the employee's to use. A role without the permission
// does not exist yet in a browser: what it gets is held by the server's tests
// (apps/reservation/tests/test_queries_contact.py) and the pages' (Vitest). What a run makes is named «E2E Rct <stamp>…»
// and deleted after it.
import { expect, test } from '@playwright/test';

import { signedIn } from './flow-helpers';
import { A, api, capture, EMPLOYEE, psql, shown } from './helpers';
import { cleanUpTagged, guestRowInTheBook, madridDay, openTheBook } from './reservation-helpers';
import { FLOW_VIEWPORTS, ownerPage, post } from './service-helpers';

const TAG = `E2E Rct ${Date.now().toString(36).toUpperCase()}`;
/** The maximum of the book's slot this spec opens: how its clean-up knows it (slots have no name). */
const SENTINEL = 81;
const AHEAD = 2;
const DAY = madridDay(AHEAD);
const GUEST = `${TAG} Ana`;
const WAITING = `${TAG} Luis`;
const NATIONAL = `61${String(Date.now()).slice(-7)}`;
const WAITING_NATIONAL = `62${String(Date.now()).slice(-7)}`;
/** As Customers paints a Spanish number: the calling code apart and the digits in threes. */
const painted = (national: string) => `+34 ${national.slice(0, 3)} ${national.slice(3, 6)} ${national.slice(6)}`;

type Row = { guest_name: string; guest_phone: string | null };
type Page = { rows: Row[]; total: number };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/reservation/reservations');
  try {
    await openTheBook(context, { day: DAY, sentinel: SENTINEL, reason: TAG });
    await post(context, '/reservation/reservations', { guest_name: GUEST, guest_phone: NATIONAL, date: DAY.date, time: '21:00', party_size: 2 });
    await post(context, '/reservation/waitlist', { guest_name: WAITING, guest_phone: WAITING_NATIONAL, date: DAY.date, preferred_time: '21:00', party_size: 2 });
  } finally {
    await context.close();
  }
});

test.afterAll(() => {
  psql(`delete from reservation_waitlistentry where guest_name like '${TAG}%'`);
  cleanUpTagged(TAG, SENTINEL);
});

for (const viewport of FLOW_VIEWPORTS) {
  test(`the employee sees a guest's phone in the book and the waitlist at ${viewport.label}px; nobody sorts by it`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/reservation/reservations', viewport, EMPLOYEE);
    try {
      const found = await api<Page>(context, A, 'GET', `/reservation/reservations?search=${NATIONAL.slice(-6)}`);
      expect(found.data.rows.map((row) => [row.guest_name, row.guest_phone])).toEqual([[GUEST, `+34${NATIONAL}`]]);
      const filtered = await api<Page>(context, A, 'GET', `/reservation/waitlist?guest_phone=${WAITING_NATIONAL}`);
      expect([filtered.status, filtered.data.total]).toEqual([200, 1]);
      for (const path of ['/reservation/reservations', '/reservation/waitlist']) {
        expect((await api(context, A, 'GET', `${path}?sort=guest_phone`)).status).toBe(422);
      }

      const row = await guestRowInTheBook(page, { ahead: AHEAD, day: DAY }, GUEST);
      await expect(row).toBeVisible();
      if (viewport.width >= 1440) {
        await expect(shown(page).locator('[role=columnheader]', { hasText: 'Phone' })).toHaveCount(1);
        await expect(row.getByText(painted(NATIONAL))).toBeVisible();
      }
      await capture(page, `reservation-contact-book-${viewport.label}`);

      await row.click();
      const form = page.locator('[data-testid=reservation-form]');
      const phone = form.locator('[data-testid=reservation-form-guest_phone] input');
      await expect(phone).toHaveValue(`+34${NATIONAL}`);
      await expect(phone).toBeInViewport({ ratio: 1 });
      await expect(form.locator('[data-testid=reservation-form-guest_email]')).toHaveCount(1);
      await capture(page, `reservation-contact-form-${viewport.label}`);
      await form.locator('[data-testid=reservation-form-cancel]').click();

      await page.goto('/reservation/waitlist');
      const entry = shown(page).locator('[data-testid=reservation-waitlist-row]', { hasText: WAITING });
      await expect(entry).toBeVisible();
      if (viewport.width >= 1440) await expect(entry.getByText(painted(WAITING_NATIONAL))).toBeVisible();
      await capture(page, `reservation-contact-waitlist-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
