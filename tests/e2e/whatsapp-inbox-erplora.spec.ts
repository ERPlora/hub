// flow: WHATSAPP_INBOX-F03, WHATSAPP_INBOX-F08, WHATSAPP_INBOX-F34, WHATSAPP_INBOX-F38, WHATSAPP_INBOX-F32, WHATSAPP_INBOX-F10, WHATSAPP_INBOX-F11
// The inbox through the run's REAL erplora.com, in a hidden Chrome: only Meta is played (whatsapp-helpers.ts, «The
// run's real erplora.com»: what to run beside this stack). erplora.com's own test seed gives `a` its number (a made-up
// Meta permission) and pushes its photo here; then:
// - F03, F08, F34, F38: what Meta posts to erplora.com's webhook, signed as Meta signs it — a customer's message (twice:
//   one message), the owner's answer from the WhatsApp Business app, Meta's statuses of it and the option she taps —
//   reaches the open inbox through erplora.com's doors 1 and 2, without a reload; each post fails on the spot, saying
//   why, unless erplora.com handed every message it carries to this Hub (`metaHandsOver`);
// - F32: the owner's reply goes through erplora.com (door 5) to Meta, which refuses the made-up permission: the bubble
//   says «Not delivered» with erplora.com's reason, and erplora.com's next photo says the number must be reconnected;
// - F10, F11: erasing a number, in the inbox or from the customer's card, has erplora.com forget it (door 6), which
//   confirms.
// Each flow's screen in three sizes (FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12-<flow>-390|834|1440). What it creates
// is named `e2e.…` and deleted after the file; erplora.com's side lives in its own run database.
import { execFileSync } from 'node:child_process';

import { expect, type Page, test } from '@playwright/test';

import { cleanUp as cleanUpCards, inputOf } from './customer-helpers';
import { A, HUB_DIR, login, psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import {
  BUSINESS_PHONE,
  cleanUp,
  e2ePhone,
  metaGraph,
  metaHandsOver,
  metaNow,
  notice,
  PREFIX,
  restorePhoto,
  seedErplora,
} from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  // erplora.com takes `a`'s number (again, connected) and this Hub takes its photo.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
});

test.afterAll(() => {
  cleanUp();
  cleanUpCards();
  restorePhoto();
});

const TASK = 'FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12';
const rowOf = (page: Page, phone: string) => shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');
const bubbles = (page: Page, side: 'inbound' | 'outbound') =>
  panel(page).locator(`[data-testid=whatsapp-inbox-message][data-side=${side}]`);

async function shots(page: Page, flow: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${flow} ${viewport.label}`);
    await page.screenshot({ path: shot(`${TASK}-${flow}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

/** A text of the customer `phone`, as Meta posts it to erplora.com. */
const said = (phone: string, name: string, id: string, body: string) =>
  notice('messages', {
    contacts: [{ profile: { name }, wa_id: phone.slice(1) }],
    messages: [{ from: phone.slice(1), id, timestamp: metaNow(), type: 'text', text: { body } }],
  });

/** The inbox open at `phone`'s conversation, once Meta's message of her has arrived through erplora.com. */
async function arrived(page: Page, phone: string, name: string, body: string): Promise<void> {
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await metaHandsOver(page.request, said(phone, name, `${PREFIX}wamid.${Date.now()}.in`, body));
  await expect(rowOf(page, phone)).toBeVisible({ timeout: 30_000 });
}

/** The id of `phone`'s conversation. */
const conversationOf = (phone: string) => psql(`select id from whatsapp_inbox_conversation where phone = '${phone}'`);

/** How far erplora.com went with forgetting a conversation's number (door 6): `done` once it confirmed, the number
 *  kept aside to ask it gone too. */
const erasure = (id: string) =>
  psql(`select erase_status || '|' || erase_phone || '|' || phone from whatsapp_inbox_conversation where id = '${id}'`);

test('WHATSAPP_INBOX-F03, F08, F34, F38 and F32: what Meta says reaches the inbox through erplora.com, and a reply goes to Meta through it', async ({
  page,
}) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Ana ${Date.now().toString(36)}`;
  const run = Date.now();
  await login(page, A, '/whatsapp_inbox/inbox');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toBeHidden();
  await page.evaluate(() => {
    (window as unknown as { e2eNoReload: boolean }).e2eNoReload = true;
  });

  // F03: her message, posted by Meta to erplora.com, arrives live with her name and one unread; Meta posting it
  // again is still one message.
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  const first = said(phone, name, `${PREFIX}wamid.${run}.in`, 'Hola, ¿me dais cita el viernes?');
  await metaHandsOver(page.request, first);
  await expect(rowOf(page, phone)).toBeVisible({ timeout: 30_000 });
  await expect(rowOf(page, phone)).toContainText(name);
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');
  await metaHandsOver(page.request, first);
  await shots(page, 'F03', async (p) => {
    await expect(rowOf(p, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');
  });
  await rowOf(page, phone).click();
  await expect(bubbles(page, 'inbound')).toHaveCount(1);
  await expect(bubbles(page, 'inbound')).toContainText('¿me dais cita el viernes?');

  // F03: closed, her next message opens it again.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-status-closed]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Closed');
  await metaHandsOver(page.request, said(phone, name, `${PREFIX}wamid.${run}.in2`, 'Mejor por la tarde.'));
  await expect(bubbles(page, 'inbound')).toHaveCount(2, { timeout: 30_000 });
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Open');

  // F08: the owner answers from the WhatsApp Business app: Meta's echo is the business's message, «From the phone».
  const echo = `${PREFIX}wamid.${run}.echo`;
  const echoed = notice('smb_message_echoes', {
    message_echoes: [
      { from: BUSINESS_PHONE, to: phone.slice(1), id: echo, timestamp: metaNow(), type: 'text', text: { body: 'Sí, el viernes a las 17:00.' } },
    ],
  });
  await metaHandsOver(page.request, echoed);
  const answer = bubbles(page, 'outbound').filter({ hasText: 'el viernes a las 17:00' });
  await expect(answer.locator('[data-testid=whatsapp-inbox-message-from-phone]')).toHaveText('From the phone', { timeout: 30_000 });
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('—');
  await shots(page, 'F08', async () => {
    await expect(answer).toBeVisible();
  });

  // F34: Meta's statuses of it, through erplora.com, move it forward by themselves; a late «delivered» never undoes «read».
  const status = (value: string) =>
    notice('messages', { statuses: [{ id: echo, status: value, timestamp: metaNow(), recipient_id: phone.slice(1) }] });
  const state = answer.locator('[data-testid=whatsapp-inbox-message-status]');
  await metaHandsOver(page.request, status('delivered'));
  await expect(state).toContainText('Delivered', { timeout: 30_000 });
  await metaHandsOver(page.request, status('read'));
  await expect(state).toContainText('Read', { timeout: 30_000 });
  await metaHandsOver(page.request, status('delivered'));
  await shots(page, 'F34', async () => {
    await expect(state).toContainText('Read');
  });

  // F38: the option she taps on the business's message shows as her answer, with its text.
  const tapped = notice('messages', {
    messages: [
      {
        from: phone.slice(1),
        id: `${PREFIX}wamid.${run}.tap`,
        timestamp: metaNow(),
        type: 'button',
        context: { from: BUSINESS_PHONE, id: echo },
        button: { payload: 'confirm', text: 'Confirmar' },
      },
    ],
  });
  await metaHandsOver(page.request, tapped);
  const option = bubbles(page, 'inbound').filter({ hasText: 'Confirmar' });
  await expect(option).toBeVisible({ timeout: 30_000 });
  await shots(page, 'F38', async () => {
    await expect(option).toBeVisible();
  });

  // F32: the reply is kept and handed to erplora.com, which takes it to Meta; Meta refuses the seed's made-up
  // permission, so the bubble says «Not delivered» with erplora.com's reason — the one the Hub kept — and no «Retry».
  const text = panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea');
  await text.fill('Perfecto, te esperamos.');
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-send]').click();
  const reply = bubbles(page, 'outbound').filter({ hasText: 'te esperamos' });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-retry]')).toHaveCount(0);
  const kept = psql(
    `select m.status || '|' || m.error_code || '|' || m.error_message from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone}' and m.origin = 'hub' order by m.created_at desc limit 1`,
  ).split('|');
  expect(kept.slice(0, 2)).toEqual(['failed', 'whatsapp_inbox.send_refused']);
  expect(kept[2]).not.toBe('');
  await expect(reply.locator('.wa-bubble__error')).toContainText(kept[2]);
  await shots(page, 'F32', async () => {
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered');
  });

  // Meta refused the permission: erplora.com's next photo says the number must be reconnected, and the inbox follows.
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-reconnect]')).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { e2eNoReload?: boolean }).e2eNoReload === true)).toBe(true);
});

test('WHATSAPP_INBOX-F10: erasing a number in the inbox has erplora.com forget it', async ({ page }) => {
  const phone = e2ePhone();
  await login(page, A, '/whatsapp_inbox/inbox');
  await arrived(page, phone, `${PREFIX}Bea ${Date.now().toString(36)}`, 'Borrad mis datos, por favor.');
  const id = conversationOf(phone);
  await rowOf(page, phone).click();
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-erase]').click();
  const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: "Erase this number's data?" });
  await expect(confirm).toContainText(phone);
  await shots(page, 'F10', async () => {
    await expect(confirm).toBeVisible();
  });
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-erased]')).toContainText('The data of this number has been erased.');
  await expect(rowOf(page, phone)).toHaveCount(0);
  // erplora.com (door 6) confirmed: the number kept aside to ask it is gone.
  await expect.poll(() => erasure(id), { timeout: 30_000 }).toBe('done||');
});

test('WHATSAPP_INBOX-F11: erasing a customer’s card empties her conversations and has erplora.com forget her number', async ({
  page,
}) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Clara ${Date.now().toString(36)}`;
  await login(page, A, '/whatsapp_inbox/inbox');
  await arrived(page, phone, name, 'Quiero darme de baja.');
  const id = conversationOf(phone);
  await rowOf(page, phone).click();
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-create-card]').click();
  const card = panel(page).locator('[data-testid=whatsapp-inbox-detail-view-card]');
  await expect(card).toHaveAttribute('href', /\/customer\/customers\//);
  await page.goto(String(await card.getAttribute('href')));

  await shown(page).locator('[data-testid=customer-detail-erase]').click();
  const erase = shown(page).locator('[data-testid=customer-erase]');
  await inputOf(erase, 'customer-erase-reason').fill('Asked by WhatsApp (e2e)');
  await erase.locator('[data-testid=customer-erase-submit]').click();
  await page.waitForURL(/\/customer\/customers$/);
  // The worker's part: the outbox relay hands `customer.customer.erased` to the inbox's reaction, as on every tick.
  execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY], { cwd: HUB_DIR, encoding: 'utf8' });

  await page.goto('/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-row]')).toHaveCount(0);
  await shots(page, 'F11', async (p) => {
    await expect(shown(p).locator('[data-testid=whatsapp-inbox-search] input')).toBeVisible();
  });
  await expect.poll(() => erasure(id), { timeout: 30_000 }).toBe('done||');
});

/** Delivers every pending `customer.customer.erased` to the inbox, as the outbox relay does on every tick. */
const RELAY = `
from django.db import transaction
from live.models import OutboxEvent
from base import relay
for event in OutboxEvent.objects.filter(name="customer.customer.erased").order_by("created_at"):
    with transaction.atomic():
        relay.deliver("whatsapp_inbox", event)
`;
