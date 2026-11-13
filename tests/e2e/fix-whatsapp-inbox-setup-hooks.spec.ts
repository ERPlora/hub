// flow: WHATSAPP_INBOX-F09
// The WhatsApp inbox's counter of the bell (the old module's `bell`,
// the old hub's bell): on the Home of hub `a`, as its owner reads
// it in Spanish, a customer writes on WhatsApp and the bell's badge counts her without a reload; opened, the row
// «Clientes de WhatsApp esperando respuesta (N)» leads to the inbox, where the owner answers her from the composer, and
// the badge goes down by itself. In each of the three sizes, leaving the capture `<KEY>-<width>`
// with the bell open. erplora.com's pushes (the customer's message, the number connected) run as its doors do
// (whatsapp-helpers.ts); nothing seeds erplora.com, so `a`'s photo stays as it was. What it creates (`e2e.` numbers and
// names, the number's row) is removed before and after.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, badgeSays, capturedFitting, openBell, psql, shown } from './helpers';
import { spanishOwnerOnMyApps as spanishOwner, streamsQuiet as settled } from './home-helpers';
import { FLOW_VIEWPORTS } from './service-helpers';
import { cleanUp, e2ePhone, keepPhoto, PREFIX, pushChannel, receive, restorePhoto } from './whatsapp-helpers';

const KEY = 'FIX-WHATSAPP_INBOX-SETUP-HOOKS';
const RUN = Date.now().toString(36);
const LABEL = 'Clientes de WhatsApp esperando respuesta';

test.beforeAll(() => {
  keepPhoto();
  cleanUp();
});
test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

interface Counter {
  key: string;
  count: number;
}

/** What the bell counts now, as the server says (`base.bell.counters`). */
async function counters(context: BrowserContext): Promise<{ total: number; waiting: number }> {
  const res = await api<{ counters: Counter[] }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  const total = res.data.counters.reduce((sum, counter) => sum + counter.count, 0);
  const waiting = res.data.counters.find((counter) => counter.key === 'whatsapp_inbox.awaiting_reply')?.count ?? 0;
  return { total, waiting };
}

const waitingRow = (page: Page): Locator =>
  page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: new RegExp(`^\\s*${LABEL} \\(\\d+\\)\\s*$`) });
const rowOf = (page: Page, contact: string): Locator =>
  shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: contact });
const panel = (page: Page): Locator => shown(page).locator('[data-testid=whatsapp-inbox-detail]');

/** The badge says `total`, or is not shown at zero. */
FLOW_VIEWPORTS.forEach(({ label, width, height }) => {
  test(`WHATSAPP_INBOX-F09: the bell counts «${LABEL}»: a customer writing counts live, leads to the inbox and goes once answered — ${label}`, async ({
    browser,
  }) => {
    // erplora.com says the number is connected (each test again: a refused delivery may change it).
    pushChannel({ status: 'connected' });
    const phone = e2ePhone();
    const name = `${PREFIX}Lucía ${label} ${RUN}`;
    const { context, page, streams } = await spanishOwner(browser, { width, height });
    try {
      const before = await counters(context);
      // The Home as it is read: its panels answered and its stream settled, before anything changes the bell.
      await expect(shown(page).locator('[data-testid="widget-board"] [data-testid="widget"]').first()).toBeVisible();
      await expect(shown(page).locator('[data-testid="widget-board"] [data-testid="widget"][aria-busy="true"]')).toHaveCount(0);
      await settled(streams);
      await badgeSays(page, before.total);
      const onTheHome = streams.length;

      // The customer writes: counted without a reload, over the stream already open (her message re-runs the bell).
      const { conversation_id: conversation } = receive(phone, 'Hola, ¿tenéis hora mañana a las 17:00?', name);
      await badgeSays(page, before.total + 1);
      expect(streams.length, 'the message reached the bell without a new /api/live').toBe(onTheHome);

      // The capture: the Home with the bell open.
      await openBell(page);
      const row = waitingRow(page);
      await expect(row).toHaveText(`${LABEL} (${before.waiting + 1})`);
      await expect(row).toHaveAttribute('data-reachable', 'true');
      await capturedFitting(page, `${KEY}-${label}`, label);

      // The row leads to the inbox, where she is.
      await row.click();
      await expect(page).toHaveURL(`${A}/whatsapp_inbox/inbox`);
      await rowOf(page, name).click();
      await expect(page).toHaveURL(new RegExp(`conversation=${conversation}`));
      const text = panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea');
      await expect(text).toBeEnabled();
      await settled(streams);
      const inTheInbox = streams.length;

      // The owner answers from the composer: the bell, in the inbox's bar too, takes her away without a reload.
      await text.fill('¡Hola! Sí, a las 17:00 tenemos hueco.');
      await panel(page).locator('[data-testid=whatsapp-inbox-composer-send]').click();
      await expect(text).toHaveValue('');
      await badgeSays(page, before.total);
      expect(streams.length, 'the answer reached the bell without a new /api/live').toBe(inTheInbox);
      expect(psql(`select last_message_direction from whatsapp_inbox_conversation where id = '${conversation}'`)).toBe('outbound');
      if (before.waiting === 0) {
        await openBell(page);
        await expect(page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: LABEL })).toHaveCount(0);
      }
    } finally {
      await context.close();
    }
  });
});
