// flow: WHATSAPP_INBOX-F09
// The WhatsApp inbox's counter of the bell (FIX-WHATSAPP_INBOX-SETUP-HOOKS; the old module's `bell`, whatsapp_inbox#244,
// hub#1678; the old hub's bell, docs/reference/old-hub/notifications-*.png): on the Home of hub `a`, as its owner reads
// it in Spanish, a customer writes on WhatsApp and the bell's badge counts her without a reload; opened, the row
// «Clientes de WhatsApp esperando respuesta (N)» leads to the inbox, where the owner answers her from the composer, and
// the badge goes down by itself. In each of the three sizes, leaving the capture `FIX-WHATSAPP_INBOX-SETUP-HOOKS-<width>`
// with the bell open. erplora.com's pushes (the customer's message, the number connected) run as its doors do
// (whatsapp-helpers.ts); nothing seeds erplora.com, so `a`'s photo stays as it was. What it creates (`e2e.` numbers and
// names, the number's row) is removed before and after.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, bellBadge, horizontalOverflow, login, openBell, psql, shot, shown, untilStill } from './helpers';
import { FLOW_VIEWPORTS } from './service-helpers';
import { cleanUp, e2ePhone, PREFIX, pushChannel, receive } from './whatsapp-helpers';

const KEY = 'FIX-WHATSAPP_INBOX-SETUP-HOOKS';
const RUN = Date.now().toString(36);
const LABEL = 'Clientes de WhatsApp esperando respuesta';

test.beforeAll(() => cleanUp());
test.afterAll(() => cleanUp());

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

/**
 * The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home, with
 * the instant of every `/api/live` the page opens: a new stream brings every result again, so a count that changes
 * without one came over the stream already open, re-run by the counter's own events.
 */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page; streams: number[] }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** Waits until the page has opened no `/api/live` for a second: every subscription of the screen is declared. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(1_000);
}

const badge = (page: Page): Locator => bellBadge(page);
const waitingRow = (page: Page): Locator =>
  page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: new RegExp(`^\\s*${LABEL} \\(\\d+\\)\\s*$`) });
const rowOf = (page: Page, contact: string): Locator =>
  shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: contact });
const panel = (page: Page): Locator => shown(page).locator('[data-testid=whatsapp-inbox-detail]');

/** The badge says `total`, or is not shown at zero. */
async function badgeSays(page: Page, total: number): Promise<void> {
  if (total > 0) await expect(badge(page)).toHaveText(String(total));
  else await expect(badge(page)).toHaveCount(0);
}

FLOW_VIEWPORTS.forEach(({ label, width, height }) => {
  test(`${KEY} WHATSAPP_INBOX-F09 la campana cuenta «${LABEL}»: a customer writing counts live, leads to the inbox and goes once answered — ${label}`, async ({
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
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${label}`) });

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
