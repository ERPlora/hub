// What the Online booking specs share: the cast (Appointments' salon, `openForACut`, with the booking page on), the
// clean-up of a spec's rows by the name they carry, and the settings of Appointments and of the page read before a spec
// and put back after it.
import { type Browser, type BrowserContext, expect, test } from '@playwright/test';

import { openForACut, salonCleanUp } from './appointment-helpers';
import { A, api, psql } from './helpers';
import { ownerPage, post } from './service-helpers';

/** Removes every row a spec named `tag…`: its bookings, the salon (`salonCleanUp`) and its customers. */
function cleanUp(tag: string): void {
  const customers = `select id from customer_customer where name like '${tag}%'`;
  psql(
    [
      `delete from online_booking_booking where appointment_id in (select id from appointment_appointment where customer_id in (${customers}))`,
      ...salonCleanUp(tag),
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${tag}%'`,
    ].join('; '),
  );
}

/** The diary's rules the page's settings also change: put back with Appointments' settings, not the page's. */
const RULES = ['min_booking_notice', 'max_advance_booking', 'slot_interval', 'auto_confirm_online', 'allow_customer_cancellation', 'cancellation_notice_hours'];

/** What the business had before a spec: the rules of Appointments and the page's own settings. */
interface Settings {
  rules: Record<string, unknown>;
  page: Record<string, unknown>;
}

async function readSettings(browser: Browser): Promise<Settings> {
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    const rules = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    const page = await api<Record<string, unknown>>(context, A, 'GET', '/online_booking/settings');
    expect([rules.status, page.status]).toEqual([200, 200]);
    return {
      rules: Object.fromEntries(Object.entries(rules.data).filter(([key]) => key !== 'timezone')),
      page: Object.fromEntries(Object.entries(page.data).filter(([key]) => key !== 'timezone' && !RULES.includes(key))),
    };
  } finally {
    await context.close();
  }
}

async function putBack(browser: Browser, saved: Settings | null): Promise<void> {
  if (!saved) return;
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    await post(context, '/appointment/settings', saved.rules, 200);
    await post(context, '/online_booking/settings', saved.page, 200);
  } finally {
    await context.close();
  }
}

/** The spec's hooks: what it named `tag…` removed before and after it, and the business's settings put back after it. */
export function keepTheBusiness(tag: string): void {
  let saved: Settings | null = null;
  test.beforeAll(async ({ browser }) => {
    cleanUp(tag);
    saved = await readSettings(browser);
  });
  test.afterAll(async ({ browser }) => {
    cleanUp(tag);
    await putBack(browser, saved);
  });
}

export type Cast = Awaited<ReturnType<typeof openForACut>>;

/** The salon (a service a professional performs, `day` open; every row named `tag …`) and the page on: bookings wait
 *  for the business to confirm them, and the customer may cancel up to 24 h before. */
export async function cast(context: BrowserContext, tag: string, day: string): Promise<Cast> {
  const salon = await openForACut(context, tag, day);
  await post(context, '/online_booking/settings', { is_enabled: true, auto_confirm_online: false, allow_customer_cancellation: true, cancellation_notice_hours: 24 }, 200);
  return salon;
}
