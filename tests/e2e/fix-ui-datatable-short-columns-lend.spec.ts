// flow: APPOINTMENT-F12, APPOINTMENT-F13 — at 1280×720 «Repeating» cut the professional's header («PROFESSIO…») and, in
// English, the time of the repetition («5:30 …»), while «Service» and «Ends» had room to spare. The header was measured
// before Ionic gave its sort icon a size, which only a real browser shows, and a short column never gave up its floor.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { aMonday, openForACut, salonCleanUp } from './appointment-helpers';
import { psql, record, shot, shown, signedInSpanish, untilStill } from './helpers';
import { ownerPage, post } from './service-helpers';
import { steady } from './table-columns';

const KEY = 'FIX-UI-DATATABLE-SHORT-COLUMNS-LEND';
const TAG = 'E2L';
const SIZE = { width: 1280, height: 720 };
const AGENDA = '/appointment/agenda';

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const series = `select id from appointment_recurring where customer_id in (${customers})`;
  const [history, lines, appointments, ...salon] = salonCleanUp(TAG);
  psql(
    [
      history,
      lines,
      appointments,
      `delete from appointment_recurringservice where recurring_id in (${series})`,
      `delete from appointment_recurring where id in (${series})`,
      ...salon,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, AGENDA);
  try {
    const { service, member } = await openForACut(context, TAG, aMonday(), 'Gil');
    const customer = await post<{ id: string }>(context, '/customer/customers', { name: `${TAG} Laura Ruiz` });
    await post(context, '/appointment/recurring', {
      customer_id: customer.id,
      services: [{ service_id: service.id }],
      staff_id: member.id,
      frequency: 'weekly',
      day_of_week: 2,
      start_date: aMonday(),
      time: '17:30',
    });
  } finally {
    await context.close();
  }
});

test.afterAll(cleanUp);

/** «Repeating» as it is first painted. A search would paint the table again, and by then its icons have their size. */
async function repeating(page: Page): Promise<Locator> {
  const view = shown(page);
  await view.locator('[data-testid=appointment-toolbar-view-series]').click();
  await view.locator('[data-testid=appointment-series-row]', { hasText: TAG }).waitFor();
  await untilStill(page);
  return view.locator('.data-table').first();
}

for (const lang of ['en', 'es'] as const) {
  test(`UI DataTable short columns at 1280 (${lang}): every header and cell of «Repeating» is whole`, async ({ browser }) => {
    const { context, page } = lang === 'en' ? await ownerPage(browser, AGENDA, SIZE) : await signedInSpanish(browser, SIZE, AGENDA);
    try {
      const seen = await steady(await repeating(page));
      record(`${KEY}-${lang}`, seen);
      for (const column of seen.columns) {
        expect(column.cut, `«${column.label}» cuts nothing: ${JSON.stringify(seen.columns)}`).toEqual([]);
        expect(column.drift, `«${column.label}» lines up with its cells`).toBeLessThanOrEqual(1);
      }
      const professional = lang === 'en' ? 'Professional' : 'Profesional';
      const ends = lang === 'en' ? 'Ends' : 'Termina';
      expect(seen.columns.map((column) => column.label), 'no column is given up for it').toEqual(expect.arrayContaining([professional, ends]));
      expect(seen.overflow, 'nothing scrolls sideways').toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${lang}`) });
    } finally {
      await context.close();
    }
  });
}
