// flow: KITCHEN-F05/F16
// A round fired by Sales tells the installed device once with its destination and dishes; a tap opens
// Kitchen, and a reload does not tell it again. Tauri is simulated only at the native bridge; the Hub,
// SaaS, live stream and database are real. Checked at the three required viewports.
import { expect, test } from '@playwright/test';

import {
  expectNoRepeatOnReload,
  nativeApp,
  notified,
  startDeviceNotices,
  tapNotification,
} from './device-notice-helpers';
import { A, api, capture, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage, post, settled } from './service-helpers';

const STAMP = stamp();
const CHECK = `e2e kitchen notice ${STAMP}`;
const VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
] as const;

function cleanUp(): void {
  cleanSales();
  cleanInventory();
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

VIEWPORTS.forEach(({ label, width, height }) => {
  test(`a new kitchen ticket notifies once and its tap opens Kitchen — ${label}`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/', { width, height });
    try {
      await context.addInitScript(nativeApp);
      await startDeviceNotices(page);

      const dish = await createProduct(context, {
        sku: `E2E-KIT-NOTICE-${STAMP}-${label}`,
        name: `E2E Kit Notice ${STAMP} Burger ${label}`,
      });
      const order = await post<{ id: string }>(context, '/sale/orders', { label: CHECK });
      await post(
        context,
        '/sale/orders/add_line',
        { order_id: order.id, product_id: dish.id, quantity: '1' },
        200,
      );
      const fired = await post<{ order: { lines: { id: string }[] } }>(
        context,
        '/sale/orders/fire',
        { order_id: order.id },
        200,
      );
      const ticketId = fired.order.lines[0].id;

      await expect.poll(() => notified(page).then((sent) => sent.length)).toBe(1);
      const [notice] = await notified(page);
      expect(notice.title).toBe(`New kitchen ticket · ${CHECK}`);
      expect(notice.body).toContain(dish.name);
      expect(notice.body).toContain(' · Waiter: ');
      expect(notice.path).toBe('/kitchen/display');
      expect(notice.id).toEqual(expect.any(Number));
      const server = await api<{ rows: { id: string }[] }>(
        context,
        A,
        'GET',
        '/kitchen/tickets/notices',
      );
      expect(server.status).toBe(200);
      expect(server.data.rows.map((row) => row.id)).toContain(ticketId);

      await tapNotification(page, notice.id);
      await expect(page).toHaveURL(/\/kitchen\/display$/);
      await expect(shown(page).locator(`[data-testid=kitchen-card-${ticketId}]`)).toBeVisible();
      await settled(page);
      await capture(page, `KITCHEN-DEVICE-NOTICE-${label}`);

      await expectNoRepeatOnReload(page);
    } finally {
      await context.close();
    }
  });
});
