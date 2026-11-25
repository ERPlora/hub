// flow: APPOINTMENT-F17, SALE-F26 — «Charge» on the appointment of a customer with a card: the check the till opens is
// already hers (her chip, not «No table or customer»), the sale charged by card is hers in Sales, and the notice that
// adds the purchase to her card names her (the e2e stack's worker does not relay it to Customers: the card's figures are
// the integration tests'). Everything the run creates is named «e2e Apt Customer <stamp>…», which the sales clean-up
// also knows its check's lines by, and is deleted after it.
import { expect, test } from '@playwright/test';

import { aMonday, openForACut, salonCleanUp } from './appointment-helpers';
import { cardDeletes, spanishMobile } from './customer-helpers';
import { pickDay } from './date-time-fields';
import { A, api, capture, psql, shown } from './helpers';
import { chargeByCard } from './sale-charge-helpers';
import { checkAtEachSize, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';
import { FLOW_VIEWPORTS, ownerPage, post, rowAction } from './service-helpers';

const TAG = `e2e Apt Customer ${stamp()}`;
const DAY = aMonday();

function cleanUp(): void {
  cleanSales();
  psql([...salonCleanUp(TAG), ...cardDeletes(`select id from customer_customer where name like '${TAG}%'`)].join('; '));
}

test.beforeAll(cleanUp);
test.afterAll(() => {
  cleanUp();
  restoreDrawer();
});

test('«Charge» on a customer’s appointment puts her on the till’s check, and the sale charged is hers', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    await drawerOff(context);
    const { service, member } = await openForACut(context, TAG, DAY);
    const card = await post<{ id: string; name: string }>(context, '/customer/customers', { name: `${TAG} Marta`, phone: spanishMobile() });
    const booked = await post<{ id: string; number: string }>(context, '/appointment/appointments', {
      customer_id: card.id,
      services: [{ service_id: service.id }],
      staff_id: member.id,
      start: `${DAY}T10:00`,
    });

    await pickDay(page, shown(page).locator('[data-testid=appointment-toolbar-calendar]'), DAY);
    await rowAction(page, 'appointment-list', booked.id, 'charge');
    await page.waitForURL(/\/sale\/pos/);
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`${card.name} · ${booked.number}`);
    await checkAtEachSize(page, FLOW_VIEWPORTS, async (label) => {
      await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(card.name);
      await expect(shown(page).locator('[data-testid=pos-check-context-empty]')).toHaveCount(0);
      await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/20[.,]00/);
      await capture(page, `appointment-charge-customer-pos-${label}`);
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    const methods = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
    const byCard = methods.data.rows.find((row) => row.type === 'card')?.id ?? '';
    await chargeByCard(page, byCard, /20[.,]00/);
    const orderId = psql(`select order_id from appointment_appointment where id = '${booked.id}'`);
    const [saleId, customerId] = psql(`select id || ' ' || coalesce(customer_id::text, '-') from sale_sale where order_id = '${orderId}'`).split(' ');
    expect(customerId).toBe(card.id);
    const completed = `select payload->>'customer_id' from live_outboxevent where name = 'sale.sale.completed' and payload->>'sale_id' = '${saleId}'`;
    expect(psql(completed)).toBe(card.id);

    await page.goto(`${A}/sale/sales`);
    await expect(shown(page).locator(`[data-testid=sales-table-row][data-id="${saleId}"]`)).toContainText(card.name);
    await capture(page, 'appointment-charge-customer-sales-1440');
  } finally {
    await context.close();
  }
});
