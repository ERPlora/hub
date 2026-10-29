// flow: internal-whatsapp-doors
// erplora.com's WhatsApp doors into the Hub, in a hidden Chrome (README «Las puertas de WhatsApp»; the contract is
// apps/whatsapp_inbox/WORKBOOK.md, «Contrato con el SaaS», doors 1–3). With the inbox of hub `a` open, the spec calls
// the doors as erplora.com does — over HTTP, signed with the stack's INTERNAL_SHARED_SECRET (HMAC-SHA256 of
// `<timestamp>.<body>`) — and the page follows by itself, never reloaded: the number connected (`PUT …/channel`)
// lifts «WhatsApp is not connected»; a customer's message (`POST …/inbound`) arrives with its unread; the same
// WhatsApp id again is `created: false` and adds nothing; an unsigned call is 401 and adds nothing; the echo of the
// owner's reply from the phone shows in the thread, and Meta's «read» (`POST …/status`) marks it «Read». The first door
// is called before anything else asked which apps are on (a fresh runserver: the cache of the apps off is cold) and on
// 127.0.0.1, a host that opens no database context: it answers 200, never 500
// (FIX-HUB-BASE-INTERNAL-WHATSAPP-DOORS-500-ON-COLD-ACTIVATION-CACHE). The final screen in three sizes
// (`${SHOTS}-390|834|1440`). What it creates is deleted after the file.
import { createHmac } from 'node:crypto';

import { expect, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';
import { cleanUp, e2ePhone, PREFIX, waId } from './whatsapp-helpers';

/** The name of the final screen's shots. */
const SHOTS = 'FIX-HUB-BASE-INTERNAL-WHATSAPP-DOORS-500-ON-COLD-ACTIVATION-CACHE';

/** The secret this stack's Hub signs `/internal` with (its local default unless the run exports another). */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';

/** Above the channel versions of whatsapp-helpers.ts (900 000 000 + …): what this spec pushes wins, and cleanUp finds it. */
let version = 950_000_000 + (Math.floor(Date.now() / 1000) % 1_000_000);

interface DoorAnswer {
  status: number;
  body: Record<string, unknown>;
}

/** Calls a WhatsApp door of the stack's Hub as erplora.com does (v1 signature over the body), or unsigned. */
async function door(method: 'POST' | 'PUT', path: string, body: unknown, secret: string | null = SECRET): Promise<DoorAnswer> {
  const raw = JSON.stringify(body);
  const timestamp = String(Math.floor(Date.now() / 1000));
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp };
  if (secret !== null) {
    headers['X-Erplora-Signature'] = createHmac('sha256', secret).update(`${timestamp}.${raw}`).digest('hex');
  }
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/whatsapp/${path}`, { method, headers, body: raw });
  const text = await response.text();
  try {
    return { status: response.status, body: JSON.parse(text) as Record<string, unknown> };
  } catch {
    // Django's own page (a door that is not mounted answers its HTML 404): said, not a parse error.
    return { status: response.status, body: { notJson: text.slice(0, 120) } };
  }
}

/** Door 1: what erplora.com pushes for a message of `phone` (E.164) in hub `a`. */
const message = (wamid: string, phone: string, text: string, over: Record<string, unknown> = {}) => ({
  hub: 'a',
  wa_message_id: wamid,
  from: phone.replace('+', ''),
  contact_name: `${PREFIX}Lucía`,
  direction: 'inbound',
  source: 'live',
  type: 'text',
  text,
  sent_at: new Date().toISOString(),
  payload: { id: wamid },
  ...over,
});

/** Door 3: the number's state in hub `a`, a version above the last one. */
function channel(status: 'not_connected' | 'connected') {
  version += 1;
  return {
    hub: 'a',
    version,
    status,
    phone_number: status === 'connected' ? '+34910000000' : '',
    display_name: status === 'connected' ? `${PREFIX}Peluquería` : '',
    monthly_limit: 150,
    monthly_usage: 3,
    usage_month: new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' }).slice(0, 7),
    templates: null,
  };
}

const rowOf = (page: Page, phone: string) => shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone });
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');
const bubbles = (page: Page, side: 'inbound' | 'outbound') => panel(page).locator(`[data-testid=whatsapp-inbox-message][data-side=${side}]`);

test.afterAll(() => {
  cleanUp();
});

test('erplora.com pushes WhatsApp through the signed doors and the open inbox follows without a reload (internal-whatsapp-doors)', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Lucía ${Date.now().toString(36)}`;

  // Door 3: the number not connected yet — the first question of the run about which apps are on in `a`.
  const off = await door('PUT', 'channel', channel('not_connected'));
  expect(off).toEqual({ status: 200, body: { applied: true, version } });

  await login(page, A, '/whatsapp_inbox/inbox');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toContainText('WhatsApp is not connected');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  // The page is never reloaded from here on (a reload would drop this mark): what changes arrives through its
  // open live stream.
  await page.evaluate(() => {
    (window as unknown as { e2eNoReload: boolean }).e2eNoReload = true;
  });
  const notReloaded = () => page.evaluate(() => (window as unknown as { e2eNoReload?: boolean }).e2eNoReload === true);

  // Door 3 again: erplora.com reports the number connected; the notice goes by itself.
  expect((await door('PUT', 'channel', channel('connected'))).body).toEqual({ applied: true, version });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toBeHidden();

  // Door 1: the customer writes; her conversation arrives with its unread.
  const first = waId();
  const arrived = await door('POST', 'inbound', message(first, phone, 'Hola, ¿me dais cita el viernes?', { contact_name: name }));
  expect(arrived.status).toBe(200);
  expect(arrived.body).toMatchObject({ created: true });
  await expect(rowOf(page, phone)).toBeVisible();
  await expect(rowOf(page, phone)).toContainText(name);
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');

  // The same WhatsApp id again (erplora.com retrying): 200, not created, nothing more to read.
  const again = await door('POST', 'inbound', message(first, phone, 'Hola, ¿me dais cita el viernes?', { contact_name: name }));
  expect(again).toEqual({ status: 200, body: { ...arrived.body, created: false } });
  // Unsigned, or signed with another secret: 401, and nothing arrives.
  for (const secret of [null, 'not-the-secret']) {
    const refused = await door('POST', 'inbound', message(waId(), phone, 'Forged'), secret);
    expect(refused.status).toBe(401);
    expect((refused.body.error as { code: string }).code).toBe('internal.unsigned');
  }

  // Opening it shows her message once.
  await rowOf(page, phone).click();
  await expect(bubbles(page, 'inbound')).toHaveCount(1);
  await expect(bubbles(page, 'inbound')).toContainText('¿me dais cita el viernes?');
  await expect(panel(page)).not.toContainText('Forged');

  // Door 1, the echo of the owner's reply from the phone app: a message of the business, «Sent».
  const echo = waId();
  const echoed = await door('POST', 'inbound', message(echo, phone, 'Sí, el viernes a las 10:00.', { direction: 'outbound', contact_name: '' }));
  expect(echoed.body).toMatchObject({ created: true });
  const reply = bubbles(page, 'outbound').filter({ hasText: 'el viernes a las 10:00' });
  await expect(reply).toBeVisible();
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-from-phone]')).toBeVisible();
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Sent');

  // Door 2: Meta says she read it.
  const read = await door('POST', 'status', { hub: 'a', wa_message_id: echo, status: 'read', status_at: new Date().toISOString() });
  expect(read).toEqual({ status: 200, body: { updated: true, status: 'read' } });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Read');
  expect(await notReloaded()).toBe(true);

  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Read');
    await settled(page);
    await noHorizontalScroll(page, `${SHOTS} ${viewport.label}`);
    await page.screenshot({ path: shot(`${SHOTS}-${viewport.label}`) });
  }
});
