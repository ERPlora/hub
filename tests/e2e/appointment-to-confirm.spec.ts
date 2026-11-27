// flow: APPOINTMENT-F03 — «N to confirm» and the bell's «Confirm the appointments» show every booking still waiting for
// confirmation, whatever its day: the agenda used to stay on today with the status filter and say «No appointments for
// this day.» while the notice counted one of another day (hub#2640). The booking of another day is listed with its day,
// «Confirm» takes it off the list, and «Back to the agenda» brings the day back. Everything the run makes is named
// «e2e Apt ToConfirm <stamp>…» and is deleted after it, and the setting it changes goes back as it was.
import { expect, type Page, test } from '@playwright/test';

import { aMonday, openForACut, salonCleanUp } from './appointment-helpers';
import { cardDeletes, spanishMobile } from './customer-helpers';
import { A, api, capture, psql, shown } from './helpers';
import { stamp } from './sale-helpers';
import { FLOW_VIEWPORTS, ownerPage, post, rowAction } from './service-helpers';

const TAG = `e2e Apt ToConfirm ${stamp()}`;
const DAY = aMonday();
let autoConfirm: boolean | undefined;

function cleanUp(): void {
  psql([...salonCleanUp(TAG), ...cardDeletes(`select id from customer_customer where name like '${TAG}%'`)].join('; '));
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** The row of the booking `id` in the agenda's list. */
const rowOf = (page: Page, id: string) => shown(page).locator(`[data-testid=appointment-list-row][data-id="${id}"]`).first();

test('«N to confirm» and the bell list the booking of another day to confirm, and «Confirm» takes it off', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    const settings = await api<{ auto_confirm_online: boolean }>(context, A, 'GET', '/appointment/settings');
    autoConfirm = settings.data.auto_confirm_online;
    await post(context, '/appointment/settings', { auto_confirm_online: false }, 200);
    const { service, member } = await openForACut(context, TAG, DAY);
    const card = await post<{ id: string }>(context, '/customer/customers', { name: `${TAG} Marta`, phone: spanishMobile() });
    const booked = await post<{ id: string; status: string }>(context, '/appointment/appointments', {
      customer_id: card.id,
      services: [{ service_id: service.id }],
      staff_id: member.id,
      start: `${DAY}T12:00`,
      source: 'online',
    });
    expect(booked.status).toBe('pending');
    // Its whole date, as the agenda writes a date in a table: a list of any day says the month too.
    const date = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${DAY}T00:00:00Z`));

    const toConfirm = shown(page).locator('[data-testid=appointment-toolbar-to-confirm]');
    await expect(toConfirm).toContainText('to confirm');
    await toConfirm.click();
    await expect(shown(page).locator('[data-testid=appointment-to-confirm-notice]')).toBeVisible();
    await expect(rowOf(page, booked.id)).toContainText(`${date} · 12:00`);
    await expect(shown(page).locator('[data-testid=appointment-toolbar-calendar]')).toHaveCount(0);
    for (const vp of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(rowOf(page, booked.id)).toBeVisible();
      await capture(page, `appointment-to-confirm-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    await shown(page).locator('[data-testid=appointment-to-confirm-back]').click();
    await expect(shown(page).locator('[data-testid=appointment-toolbar-calendar]')).toBeVisible();
    await expect(shown(page).locator('[data-testid=appointment-to-confirm-notice]')).toHaveCount(0);

    // The bell's «Confirm the appointments» leads to the same list.
    await page.goto(`${A}/appointment/agenda?to_confirm=1`);
    await expect(rowOf(page, booked.id)).toBeVisible();
    await expect(page).toHaveURL(/\/appointment\/agenda$/);

    await rowAction(page, 'appointment-list', booked.id, 'confirm');
    await expect.poll(() => psql(`select status from appointment_appointment where id = '${booked.id}'`)).toBe('confirmed');
    await expect(rowOf(page, booked.id)).toHaveCount(0);
  } finally {
    if (autoConfirm !== undefined) await post(context, '/appointment/settings', { auto_confirm_online: autoConfirm }, 200);
    await context.close();
  }
});
