// flow: SALE-F26, APPOINTMENT-F17 — «Charge» on an appointment opens the till on that appointment's check and nothing
// else: until it is on screen with its customer the till says «Opening the check…», with neither the catalogue nor
// another check (not the one the device had, not an empty one), so nothing is added to or charged on the wrong check.
// A check that cannot be opened is said in its place, and «Continue» gives the till back. Everything the run creates
// is named «e2e Apt Opens <stamp>…» and deleted before and after it.
import { type Page, expect, test } from '@playwright/test';

import { aMonday, cleanSalonAndCards, openForACut } from './appointment-helpers';
import { spanishMobile } from './customer-helpers';
import { pickDay } from './date-time-fields';
import { A, shown } from './helpers';
import { stamp } from './sale-helpers';
import { capturedAtSizes, FLOW_VIEWPORTS, ownerPage, post, rowAction } from './service-helpers';

const TAG = `e2e Apt Opens ${stamp()}`;
const DAY = aMonday();

test.beforeAll(() => cleanSalonAndCards(TAG));
test.afterAll(() => cleanSalonAndCards(TAG));

interface Paint {
  opening: boolean;
  catalogue: boolean;
  title: string | null;
  customer: string | null;
  noContext: boolean;
}

/** From now on, each change of the page records what the till paints: «Opening the check…», the catalogue, and the
 *  check column's title, customer chip and «No table or customer». */
async function recordTill(page: Page): Promise<void> {
  await page.evaluate(() => {
    const paints: Paint[] = [];
    (window as unknown as { tillPaints: Paint[] }).tillPaints = paints;
    const look = (): void => {
      const cart = document.querySelector('[data-testid=pos-cart]');
      const opening = !!document.querySelector('[data-testid=pos-linked-loading]');
      if (!cart && !opening) return;
      paints.push({
        opening,
        catalogue: !!document.querySelector('.pos-catalog'),
        title: cart?.querySelector<HTMLInputElement>('[data-testid=pos-check-title]')?.value ?? null,
        customer: cart?.querySelector('[data-testid=pos-customer-chip]')?.textContent?.trim() ?? null,
        noContext: !!cart?.querySelector('[data-testid=pos-check-context-empty]'),
      });
    };
    new MutationObserver(look).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
  });
}

const paintsOf = (page: Page): Promise<Paint[]> => page.evaluate(() => (window as unknown as { tillPaints: Paint[] }).tillPaints);

test('«Charge» says it is opening the appointment’s check and then shows that check, never another one', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    const { service, member } = await openForACut(context, TAG, DAY);
    const card = await post<{ id: string; name: string }>(context, '/customer/customers', { name: `${TAG} Marta`, phone: spanishMobile() });
    const book = (start: string) =>
      post<{ id: string; number: string }>(context, '/appointment/appointments', {
        customer_id: card.id,
        services: [{ service_id: service.id }],
        staff_id: member.id,
        start: `${DAY}T${start}`,
      });
    const booked = await book('10:00');
    // The device was last on another appointment's check: the till would come back to it on its own.
    const other = await post<{ order_id: string }>(context, '/appointment/appointments/charge', { id: (await book('11:00')).id }, 200);
    await page.evaluate((id) => localStorage.setItem('erplora.sale.pos.currentCheck', id), other.order_id);

    await pickDay(page, shown(page).locator('[data-testid=appointment-toolbar-calendar]'), DAY);
    await recordTill(page);
    await rowAction(page, 'appointment-list', booked.id, 'charge');
    await page.waitForURL(/\/sale\/pos/);
    const title = `${card.name} · ${booked.number}`;
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(title);
    await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(card.name);

    const paints = await paintsOf(page);
    const checks = paints.filter((paint) => paint.title !== null);
    expect(checks.length, JSON.stringify(paints)).toBeGreaterThan(0);
    for (const paint of checks) {
      expect(paint, JSON.stringify(paints)).toMatchObject({ opening: false, title, noContext: false });
      expect(paint.customer, JSON.stringify(paints)).toContain(card.name);
    }
    expect(paints.filter((paint) => paint.opening).every((paint) => !paint.catalogue), JSON.stringify(paints)).toBe(true);
    expect(paints[0], JSON.stringify(paints)).toMatchObject({ opening: true });
    await capturedAtSizes(page, 'appointment-charge-opens-check', FLOW_VIEWPORTS, async () => {
      await expect(shown(page).locator('[data-testid=pos-till]')).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('while the check is on its way the till says so; one that cannot be opened is said in its place, and «Continue» gives the till back', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/sale/pos');
  try {
    await expect(shown(page).locator('.pos-catalog')).toBeVisible();
    let letGo!: () => void;
    const held = new Promise<void>((resolve) => (letGo = resolve));
    await page.route('**/api/sale/orders/detail?*', async (route) => {
      await held;
      await route.continue();
    });
    await page.goto(`${A}/sale/pos?order=019a0000-0000-7000-8000-000000000000`);
    const opening = shown(page).locator('[data-testid=pos-linked-loading]');
    await expect(opening).toHaveText('Opening the check…');
    await expect(shown(page).locator('.pos-catalog')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid=pos-cart]')).toHaveCount(0);
    await capturedAtSizes(page, 'appointment-charge-opening', FLOW_VIEWPORTS, () => expect(opening).toBeVisible());

    letGo();
    const failed = shown(page).locator('[data-testid=pos-linked-error]');
    await expect(failed).toContainText('That check is not open any more: it was charged, voided or does not exist.');
    await expect(shown(page).locator('.pos-catalog')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid=pos-cart]')).toHaveCount(0);
    await capturedAtSizes(page, 'appointment-charge-cannot-open', FLOW_VIEWPORTS, () => expect(failed).toBeVisible());

    await shown(page).locator('[data-testid=pos-linked-action]').click();
    await expect(failed).toHaveCount(0);
    await expect(shown(page).locator('.pos-catalog')).toBeVisible();
    await expect(page).toHaveURL(/\/sale\/pos$/);
  } finally {
    await context.close();
  }
});
