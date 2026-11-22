// flow: TABLE-F28, TABLE-F10 — a booking's party seated from the floor plan takes the booking's customer to the
// check: the till opened from the occupied table names her. Everything the run creates is named «E2E Tsr <stamp>…»
// and deleted after it.
import { expect, test } from '@playwright/test';

import { cardDeletes } from './customer-helpers';
import { A, api, capture, psql, shown } from './helpers';
import { openTheBook } from './reservation-helpers';
import { checkAtEachSize, stamp, zoneWithTable } from './sale-helpers';
import { ownerPage, post } from './service-helpers';
import { reservationTimes } from './table-booking';

const RUN = stamp();
const TAG = `E2E Tsr ${RUN}`;
/** The maximum of the book's slot this spec opens: how its clean-up knows it (slots have no name). */
const SENTINEL = 74;
const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '834', width: 834, height: 1112 },
  { label: '390', width: 390, height: 844 },
];

function cleanUp(): void {
  const tables = "select id from table_table where zone_id in (select id from table_zone where name like 'E2E Tsr %')";
  psql(
    [
      `create temp table e2e_tsr_sessions as select id, order_id from table_tablesession where table_id in (${tables})`,
      'delete from customer_orderlink where order_id in (select order_id from e2e_tsr_sessions)',
      'delete from table_sessionmove where session_id in (select id from e2e_tsr_sessions)',
      `delete from table_hold where table_id in (${tables})`,
      'delete from table_tablesession where id in (select id from e2e_tsr_sessions)',
      'delete from sale_order where id in (select order_id from e2e_tsr_sessions) and id not in (select order_id from sale_orderline)',
      "delete from reservation_reservation where customer_id in (select id from customer_customer where name like 'E2E Tsr %')",
      ...cardDeletes("select id from customer_customer where name like 'E2E Tsr %'"),
      `delete from table_table where id in (${tables})`,
      "delete from table_zone where name like 'E2E Tsr %'",
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      "delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like 'E2E Tsr %')",
      "delete from schedule_override where reason like 'E2E Tsr %'",
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('TABLE-F28: seating a booking from the plan puts its customer on the check the till opens', async ({ browser }) => {
  const { soon } = await reservationTimes();
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    const { zoneId, tableId } = await zoneWithTable(context, TAG, RUN);
    const card = await post<{ id: string; name: string }>(context, '/customer/customers', { name: `${TAG} Marta`, phone: `6${String(Date.now()).slice(-8)}` });
    await openTheBook(context, { day: soon, sentinel: SENTINEL, reason: `${TAG} open` });
    const booked = await post<{ id: string }>(context, '/reservation/reservations', { customer_id: card.id, date: soon.date, time: soon.time, party_size: 2, table_id: tableId });
    await post(context, '/reservation/reservations/confirm', { id: booked.id }, 200);

    const view = shown(page);
    await view.locator('[data-testid=table-floor-mode-service]').click();
    await view.locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
    const tile = view.locator(`[data-testid=table-floor-tile-${tableId}]`);
    await expect(tile).toContainText('Reserved');
    await tile.click();
    await expect(page.locator('[data-testid=table-sheet-hold]')).toContainText(card.name);
    await expect(page.locator('[data-testid=table-guests-value]')).toContainText('2');
    await page.locator('[data-testid=table-guests-confirm]').click();
    await expect(tile).toContainText('Occupied');

    const seated = await api<{ checks: { customer_name: string | null }[] }>(context, A, 'GET', `/table/tables/detail?id=${tableId}`);
    expect(seated.data.checks.map((check) => check.customer_name)).toEqual([card.name]);

    await tile.click();
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${RUN}`);
    await checkAtEachSize(page, SIZES, async (label) => {
      await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(card.name);
      await capture(page, `table-seat-reservation-customer-pos-${label}`);
    });
  } finally {
    await context.close();
  }
});
