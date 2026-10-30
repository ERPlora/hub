// flow: WHATSAPP_INBOX-F01 WHATSAPP_INBOX-F02 WHATSAPP_INBOX-F03 WHATSAPP_INBOX-F05 WHATSAPP_INBOX-F06 WHATSAPP_INBOX-F07 WHATSAPP_INBOX-F08 WHATSAPP_INBOX-F09 WHATSAPP_INBOX-F10 WHATSAPP_INBOX-F13 WHATSAPP_INBOX-F32 WHATSAPP_INBOX-F33 WHATSAPP_INBOX-F34 WHATSAPP_INBOX-F35 WHATSAPP_INBOX-F36 WHATSAPP_INBOX-F37 WHATSAPP_INBOX-F38
// The WhatsApp inbox in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the owner of hub `a` opens
// the inbox with the number not connected and reads why; a customer writes (erplora.com's push, run as
// the system) and her conversation arrives live with its unread; opening it reads it and shows the thread;
// the composer says nothing can be sent while the number is not connected, with the reason's code, and
// opens when erplora.com reports it connected; a reply is kept and handed to the run's real erplora.com, where
// erplora.com's own test seed gave `a` a number (whatsapp-helpers.ts, `seedErplora`): erplora.com takes it to Meta,
// which refuses the seed's made-up permission, and the bubble says «Not delivered» in the Hub's words, never «Sent»
// (Meta's statuses through erplora.com: whatsapp-inbox-erplora.spec.ts); a template with its variable, handed over
// the same way; a note, «Pending», «Assign to me»,
// «Create card» joining a Customers card; «Erase this number's data» asked first. An attachment, the
// echo of the owner's phone and an option tapped show in the thread; the filters keep who waits; the
// month spent and a number to reconnect are said and go by themselves. An employee notes and takes a
// conversation but neither erases nor opens Settings. «Retry» on another business's reply, from the shared inbox of
// phase 1, hands it to erplora.com at once, for that business (WHATSAPP_INBOX-F34). Each flow's screen in three sizes
// (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440). What it creates is deleted after the file.
import { execFileSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp as cleanUpCards } from './customer-helpers';
import { A, capture, EMPLOYEE, HUB_DIR, hostPage, login, psql, SAAS, shot, shown } from './helpers';
import { filterBy, FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import {
  cleanUp,
  e2ePhone,
  flowShots,
  metaGraph,
  PREFIX,
  pushChannel,
  receive,
  restorePhoto,
  seedErplora,
  template,
  waId,
} from './whatsapp-helpers';

test.beforeAll(async () => {
  // erplora.com takes `a`'s number (its test seed): what the Hub hands it reaches Meta.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
});

test.afterAll(() => {
  cleanUp();
  cleanUpCards();
  restorePhoto();
});

const rowOf = (page: Page, phone: string) => shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone });
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');
const bubbles = (page: Page, side: 'inbound' | 'outbound') => panel(page).locator(`[data-testid=whatsapp-inbox-message][data-side=${side}]`);

async function searchInbox(page: Page, text: string): Promise<void> {
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(text);
}

/** WCAG contrast of the text of `part` against its bubble (the bubble's background over white). */
async function contrast(bubble: Locator, part: string): Promise<number> {
  return bubble.evaluate((element, selector) => {
    const parse = (color: string) => (color.match(/[\d.]+/g) ?? []).map(Number);
    const [r, g, b, alpha = 1] = parse(getComputedStyle(element).backgroundColor);
    const back = [r, g, b].map((value) => value * alpha + 255 * (1 - alpha));
    const fore = parse(getComputedStyle(element.querySelector(selector) as Element).color).slice(0, 3);
    const luminance = (rgb: number[]) => {
      const [lr, lg, lb] = rgb.map((value) => {
        const v = value / 255;
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
    };
    const [high, low] = [luminance(back), luminance(fore)].sort((x, y) => y - x);
    return (high + 0.05) / (low + 0.05);
  }, part);
}

/** Picks `option` in the inbox's column filter `filter`, through its «Filters» panel (the old hub's funnel). */
async function filterInbox(page: Page, filter: string, option: string): Promise<void> {
  await filterBy(page, 'whatsapp-inbox', filter, option);
}

test('the owner reads, answers, organises and erases a WhatsApp conversation; the composer follows the number', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Ana ${Date.now().toString(36)}`;
  pushChannel({ status: 'not_connected' });

  // F01: the number not connected, and where to connect it: the inbox's own Settings (whatsapp-inbox-connect.spec.ts).
  await login(page, A, '/whatsapp_inbox/inbox');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toContainText('WhatsApp is not connected');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-go-to-settings]')).toHaveAttribute('href', '/whatsapp_inbox/settings');
  await searchInbox(page, phone.slice(3));

  // F03: the customer writes; her conversation arrives live, unread.
  receive(phone, 'Hola, ¿tenéis hora mañana por la tarde?', name);
  await expect(rowOf(page, phone)).toBeVisible();
  await expect(rowOf(page, phone)).toContainText(name);
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');
  await flowShots(page, 'WHATSAPP_INBOX-F01', async (p) => {
    await expect(shown(p).locator('[data-testid=whatsapp-inbox-go-to-settings]')).toBeVisible();
  });
  await flowShots(page, 'WHATSAPP_INBOX-F03', async (p) => {
    await expect(rowOf(p, phone)).toBeVisible();
  });

  // F05: opening it reads it and shows the thread.
  await rowOf(page, phone).click();
  await expect(panel(page)).toBeVisible();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-message]')).toContainText('¿tenéis hora mañana por la tarde?');
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('—');
  expect(new URL(page.url()).searchParams.get('conversation')).toBeTruthy();

  // F32: with the number not connected nothing can be sent, and it says why, with its code.
  const blocked = panel(page).locator('[data-testid=whatsapp-inbox-composer-blocked]');
  await expect(blocked).toContainText('WhatsApp is not connected');
  await expect(blocked).toHaveAttribute('data-code', 'not_connected');
  // An ion-button is not a native control: its state is its `disabled` property (as the other specs check).
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
  await flowShots(page, 'WHATSAPP_INBOX-F05', async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-message]')).toBeVisible();
  });

  // erplora.com reports the number connected, with its templates: the composer opens by itself.
  pushChannel({
    status: 'connected',
    templates: [template('e2e_recordatorio'), template('e2e_rechazada', { status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' })],
  });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toBeHidden();
  await expect(blocked).toBeHidden();

  // F32, F34: the reply is kept and handed to erplora.com (door 5), which takes it to Meta: Meta refuses the seed's
  // made-up permission with its 190 and erplora.com says so (409 `whatsapp.reconnect_needed`), so the bubble says
  // «Not delivered» in the Hub's words, never Meta's, and offers no «Retry» (the same key would get the same answer);
  // never «Sent» without Meta's id. The number this spec pushed stays connected (its version is above erplora.com's
  // next photo), so the bubble says only what happened to that message, with no «Reconnect».
  const text = panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea');
  await expect(text).toBeEnabled();
  await text.fill('Sí, a las 17:00 tenemos hueco.');
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-send]').click();
  const reply = bubbles(page, 'outbound').filter({ hasText: 'a las 17:00 tenemos hueco' });
  await expect(reply).toBeVisible();
  await expect(text).toHaveValue('');
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-error]')).toHaveAttribute('data-code', 'whatsapp_inbox.reconnect_needed');
  await expect(reply.locator('.wa-bubble__error')).toHaveText("WhatsApp's permission for your number had expired.");
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-retry]')).toHaveCount(0);
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-reconnect]')).toHaveCount(0);
  // What it says can be read on the business's bubble (WCAG AA, 4.5:1): the text, «Not delivered» and why.
  for (const part of ['.wa-bubble__body', '[data-testid=whatsapp-inbox-message-status]', '.wa-bubble__error']) {
    expect(await contrast(reply, part), part).toBeGreaterThanOrEqual(4.5);
  }
  await flowShots(page, 'WHATSAPP_INBOX-F32', async () => {
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered');
  });

  // F33: «Template» offers only the approved ones; its variable fills the preview, and it is sent.
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-template]').click();
  const templates = page.locator('ion-modal[data-testid=whatsapp-inbox-template-form]');
  await expect(templates).toContainText('e2e_recordatorio');
  await expect(templates).not.toContainText('e2e_rechazada');
  await templates.locator('ion-radio', { hasText: 'e2e_recordatorio' }).click();
  await templates.locator('[data-testid=whatsapp-inbox-template-variable-1] input').fill('Ana');
  await expect(templates.locator('[data-testid=whatsapp-inbox-template-preview]')).toContainText('Hola Ana, te esperamos mañana.');
  await flowShots(page, 'WHATSAPP_INBOX-F33', async () => {
    await expect(templates.locator('[data-testid=whatsapp-inbox-template-preview]')).toBeVisible();
  });
  await templates.locator('[data-testid=whatsapp-inbox-template-form-submit]').click();
  await expect(templates).toBeHidden();
  // Handed to erplora.com (door 5) like a reply: Meta refuses the seed's permission, «Not delivered» in the Hub's words.
  const sentTemplate = bubbles(page, 'outbound').filter({ hasText: 'e2e_recordatorio' });
  await expect(sentTemplate).toBeVisible();
  await expect(sentTemplate.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
  await expect(sentTemplate.locator('.wa-bubble__error')).toHaveText("WhatsApp's permission for your number had expired.");

  // F36: an internal note, in the thread.
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-mode-note]').click();
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-note] textarea').fill('Prefiere las tardes.');
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-add-note]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-note]')).toContainText('Prefiere las tardes.');
  await flowShots(page, 'WHATSAPP_INBOX-F36', async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-note]')).toBeVisible();
  });

  // F35 and F07: «Pending» and «Assign to me», on the panel and on the row.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-status-pending]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Pending');
  await expect(rowOf(page, phone)).toContainText('Pending');
  await flowShots(page, 'WHATSAPP_INBOX-F35', async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Pending');
  });
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-assign-me]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-assign-me]')).toBeHidden();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-unassign]')).toBeVisible();
  await flowShots(page, 'WHATSAPP_INBOX-F07', async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-detail-unassign]')).toBeVisible();
  });

  // F37: «Create card» makes a Customers card with her WhatsApp name and number, and joins it.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-create-card]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-customer]')).toHaveText(name);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-view-card]')).toHaveAttribute('href', /\/customer\/customers\//);
  await flowShots(page, 'WHATSAPP_INBOX-F37', async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-detail-view-card]')).toBeVisible();
  });

  // The customer writes again while the thread is open: it shows, the conversation reopens, it stays read.
  receive(phone, '¡Genial, gracias!', name);
  await expect(bubbles(page, 'inbound')).toHaveCount(2);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Open');

  // F10: «Erase this number's data» asks first, naming the number; erased, it leaves the inbox.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-erase]').click();
  const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: "Erase this number's data?" });
  await expect(confirm).toContainText(phone);
  await flowShots(page, 'WHATSAPP_INBOX-F10', async () => {
    await expect(confirm).toBeVisible();
  });
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-erased]')).toContainText('The data of this number has been erased.');
  await expect(rowOf(page, phone)).toHaveCount(0);
});

test('an attachment, the echo of the owner’s phone and an option tapped show in the thread', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Carla ${Date.now().toString(36)}`;
  pushChannel({ status: 'connected' });
  receive(phone, '¿Me dais cita?', name);
  await login(page, A, '/whatsapp_inbox/inbox');
  await searchInbox(page, phone.slice(3));
  await rowOf(page, phone).click();
  await expect(bubbles(page, 'inbound')).toHaveCount(1);

  // F06: a photo she sends is named by its kind, with its caption; erplora.com has none at this made-up address, so
  // the bubble says it could not be loaded and opens it at erplora.com in a new tab (painted: whatsapp-inbox-media.spec.ts).
  receive(phone, '', name, {
    type: 'image',
    media: { url: `${SAAS}/whatsapp/media/${PREFIX}foto.jpg`, mime_type: 'image/jpeg', filename: '', caption: 'Así lo quiero' },
  });
  const media = panel(page).locator('[data-testid=whatsapp-inbox-message-media]');
  await expect(media).toContainText('Photo');
  await expect(media).toContainText('Así lo quiero');
  await expect(media.locator('[data-testid=whatsapp-inbox-message-media-error]')).toHaveText('The image could not be loaded.');
  await expect(media.locator('a')).toHaveAttribute('href', `${SAAS}/whatsapp/media/${PREFIX}foto.jpg`);
  await expect(media.locator('a')).toHaveAttribute('target', '_blank');
  await flowShots(page, 'WHATSAPP_INBOX-F06', async () => {
    await expect(media).toBeVisible();
  });

  // F08: what the owner answers from the WhatsApp Business app shows as the business's, «From the phone».
  receive(phone, 'Claro, el jueves a las 10.', name, { direction: 'outbound' });
  const echo = bubbles(page, 'outbound').filter({ hasText: 'el jueves a las 10' });
  await expect(echo.locator('[data-testid=whatsapp-inbox-message-from-phone]')).toHaveText('From the phone');
  await flowShots(page, 'WHATSAPP_INBOX-F08', async () => {
    await expect(echo).toBeVisible();
  });

  // F38: the option she taps shows as her answer, with its text.
  receive(phone, '', name, { type: 'button', reply_to: waId(), reply: { id: 'confirm', title: 'Confirmar' } });
  await expect(bubbles(page, 'inbound').filter({ hasText: 'Confirmar' })).toBeVisible();
  await flowShots(page, 'WHATSAPP_INBOX-F38', async () => {
    await expect(bubbles(page, 'inbound').filter({ hasText: 'Confirmar' })).toBeVisible();
  });
});

test('who waits, the month spent and a number to reconnect are said, and go by themselves', async ({ page }) => {
  const waiting = e2ePhone();
  const answered = e2ePhone();
  pushChannel({ status: 'connected' });
  receive(waiting, 'Hola, ¿abrís el sábado?', `${PREFIX}Dani ${Date.now().toString(36)}`);
  receive(answered, 'Gracias por todo', `${PREFIX}Eva ${Date.now().toString(36)}`);
  await login(page, A, '/whatsapp_inbox/inbox');
  await searchInbox(page, '69900');
  await rowOf(page, answered).click();
  await expect(rowOf(page, answered).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('—');
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-close]').click();

  // F09: «Open» and «With unread» keep who waits for an answer.
  await filterInbox(page, 'status', 'Open');
  await filterInbox(page, 'unread', 'With unread');
  await expect(rowOf(page, waiting)).toBeVisible();
  await expect(rowOf(page, answered)).toHaveCount(0);
  await flowShots(page, 'WHATSAPP_INBOX-F09', async (p) => {
    await expect(rowOf(p, waiting)).toBeVisible();
  });

  // F13: the month spent is said above the list and in Settings; what customers write still arrives.
  pushChannel({ status: 'connected', monthly_limit: 150, monthly_usage: 150 });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]')).toContainText('You have used all the WhatsApp messages of your plan this month.');
  receive(waiting, '¿Seguís ahí?', `${PREFIX}Dani`);
  await expect(rowOf(page, waiting).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('2');
  await flowShots(page, 'WHATSAPP_INBOX-F13', async (p) => {
    await expect(shown(p).locator('[data-testid=whatsapp-inbox-cap-reached]')).toBeVisible();
  });
  await shown(page).locator('[data-testid=tab-settings]').click();
  await page.waitForURL(/\/whatsapp_inbox\/settings$/);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-month]')).toContainText('150 of 150 messages sent');
  await page.screenshot({ path: shot('APP-WHATSAPP_INBOX-1-WHATSAPP_INBOX-F13-settings-1280') });

  // F02: WhatsApp took the permission back: «Reconnect» is said, and goes when the number is back.
  await shown(page).locator('[data-testid=tab-inbox]').click();
  await page.waitForURL(/\/whatsapp_inbox\/inbox/);
  pushChannel({ status: 'reconnect_needed' });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-reconnect]')).toBeVisible();
  await flowShots(page, 'WHATSAPP_INBOX-F02', async (p) => {
    await expect(shown(p).locator('[data-testid=whatsapp-inbox-reconnect]')).toBeVisible();
  });
  pushChannel({ status: 'connected' });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-reconnect]')).toBeHidden();
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]')).toBeHidden();
});

test('an employee notes and takes a conversation, but neither erases nor opens the settings', async ({ browser }) => {
  const phone = e2ePhone();
  receive(phone, 'Quería cambiar mi cita', `${PREFIX}Bea ${Date.now().toString(36)}`);
  let context: BrowserContext | undefined;
  try {
    const opened = await hostPage(browser, A, { next: '/whatsapp_inbox/inbox', credentials: EMPLOYEE });
    context = opened.context;
    const page = opened.page;
    await searchInbox(page, phone.slice(3));
    await rowOf(page, phone).click();
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-message]')).toContainText('Quería cambiar mi cita');
    await panel(page).locator('[data-testid=whatsapp-inbox-composer-mode-note]').click();
    await panel(page).locator('[data-testid=whatsapp-inbox-composer-note] textarea').fill('La llamo yo.');
    await panel(page).locator('[data-testid=whatsapp-inbox-composer-add-note]').click();
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-note]')).toContainText('La llamo yo.');
    await panel(page).locator('[data-testid=whatsapp-inbox-detail-assign-me]').click();
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-unassign]')).toBeVisible();
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-erase]')).toHaveCount(0);
    await page.goto(`${A}/whatsapp_inbox/settings`);
    await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-forbidden]')).toContainText('You do not have permission');
    await page.screenshot({ path: shot('whatsapp-inbox-employee-settings') });
  } finally {
    await context?.close();
  }
});

/** `b`'s reply that erplora.com never answered («Not sent», with «Retry»), in phase 1's shared tables: `b`'s own
 *  operations, run as the platform in a one-shot `manage.py shell` (phase 1's shared database, as the helpers of
 *  whatsapp-helpers.ts do for `a`), with what their COMMIT hands to erplora.com dropped, as when the worker stops on a
 *  deploy. Its channel's version and its conversation's number carry the run's marks: `cleanUp` deletes them. */
const B_NOT_SENT = `
import json, os, uuid
from base import outbound
from live.context import Scope, system_context
from live.operations import get
from apps.whatsapp_inbox import gateway
class _Stopping:
    def submit(self, job):
        return False
    def stop(self, grace):
        return True
outbound._pool = _Stopping()
b = system_context(Scope("host", "b"))
def run(name, payload):
    op = get(name)
    return op(b, op.input.model_validate(payload))
setup = json.loads(os.environ["WA_SETUP"])
run("whatsapp_inbox.channel.sync", setup["channel"])
received = run("whatsapp_inbox.message.receive", setup["inbound"])
sent = run("whatsapp_inbox.message.send", {"id": str(received.conversation_id), "text": setup["text"], "client_message_id": str(uuid.uuid7())})
run("whatsapp_inbox.message.claim_delivery", {"id": str(sent.id)})
run("whatsapp_inbox.message.record_delivery", {"id": str(sent.id), "kind": gateway.UNREACHABLE, "message": "erplora.com did not answer."})
print(json.dumps({"id": str(sent.id)}))
`;

/** `b`'s reply to `phone` (E.164) that never left (B_NOT_SENT): its id. */
function notSentOfB(phone: string, contactName: string, text: string): string {
  const month = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' }).slice(0, 7);
  const setup = {
    channel: {
      version: 900_000_000 + (Math.floor(Date.now() / 1000) % 1_000_000),
      status: 'connected',
      phone_number: '+34910000002',
      display_name: 'e2e. Barbería',
      monthly_limit: 150,
      monthly_usage: 0,
      usage_month: month,
      templates: null,
    },
    inbound: {
      wa_message_id: waId(),
      from: phone.replace('+', ''),
      contact_name: contactName,
      direction: 'inbound',
      source: 'live',
      type: 'text',
      text: 'Hola, ¿me dais cita el viernes?',
      sent_at: new Date().toISOString(),
    },
    text,
  };
  const out = execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', B_NOT_SENT], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, WA_SETUP: JSON.stringify(setup) },
  });
  return (JSON.parse(out.trim().split('\n').at(-1) ?? '{}') as { id: string }).id;
}

test('«Retry» on another business’s reply in the shared inbox hands it to erplora.com at once, for that business', async ({ page }) => {
  // WHATSAPP_INBOX-F34 (FIX-HUB-WHATSAPP-INBOX-RETRY-OF-ANOTHER-BUSINESS-WAITS-FOR-THE-SWEEP): phase 1's inbox of `a` also
  // lists `b`'s conversations. `a`'s owner retries `b`'s reply that did not leave: `a`'s request hands it to erplora.com
  // at once, for `b` (never as `a`'s, never refused for running in `a`'s context), and erplora.com answers `b`'s way:
  // `b` has no number there (its test seed gives one only to `a`, whose answer would be Meta's 190, «reconnect»), so
  // «Not delivered», said in the Hub's words and never as Meta's reason. This stack runs no worker: no sweep could have
  // handed it over. Before, it stayed «Sending…» until the worker's sweep, 2 to 5 minutes later.
  const phone = e2ePhone();
  const text = 'Te esperamos el viernes a las 11:00.';
  const id = notSentOfB(phone, `${PREFIX}Bea ${Date.now().toString(36)}`, text);
  const state = () => psql(`select status || ' ' || error_code from whatsapp_inbox_message where id = '${id}'`);
  expect(state()).toBe('sending whatsapp_inbox.saas_unreachable');

  await login(page, A, '/whatsapp_inbox/inbox');
  await searchInbox(page, phone.slice(3));
  await rowOf(page, phone).click();
  const reply = bubbles(page, 'outbound').filter({ hasText: text });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toHaveText('Not sent');
  await reply.locator('[data-testid=whatsapp-inbox-message-retry]').click();

  await expect.poll(state, { timeout: 15_000 }).toBe('failed whatsapp_inbox.channel_not_connected');
  // erplora.com's answer is `b`'s live notice, not `a`'s (phase 1 sends them per hub): `a`'s page reads it again.
  await page.reload();
  await searchInbox(page, phone.slice(3));
  await rowOf(page, phone).click();
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toHaveText('Not delivered');
  const reason = reply.locator('[data-testid=whatsapp-inbox-message-error]');
  await expect(reason).toHaveAttribute('data-code', 'whatsapp_inbox.channel_not_connected');
  await expect(reason).toHaveText('WhatsApp is not connected: connect the number in Settings to send.');
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await reply.scrollIntoViewIfNeeded();
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toBeInViewport();
    await settled(page);
    await noHorizontalScroll(page, `WHATSAPP_INBOX-F34 retry of another business ${viewport.label}`);
    await capture(page, `FIX-HUB-WHATSAPP-INBOX-RETRY-OF-ANOTHER-BUSINESS-WAITS-FOR-THE-SWEEP-${viewport.label}`);
  }
});
