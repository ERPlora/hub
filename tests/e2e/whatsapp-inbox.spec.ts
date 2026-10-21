// flow: WHATSAPP_INBOX-F01 WHATSAPP_INBOX-F02 WHATSAPP_INBOX-F03 WHATSAPP_INBOX-F05 WHATSAPP_INBOX-F06 WHATSAPP_INBOX-F07 WHATSAPP_INBOX-F08 WHATSAPP_INBOX-F09 WHATSAPP_INBOX-F10 WHATSAPP_INBOX-F13 WHATSAPP_INBOX-F32 WHATSAPP_INBOX-F33 WHATSAPP_INBOX-F35 WHATSAPP_INBOX-F36 WHATSAPP_INBOX-F37 WHATSAPP_INBOX-F38
// The WhatsApp inbox in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the owner of hub `a` opens
// the inbox with the number not connected and reads why; a customer writes (erplora.com's push, run as
// the system) and her conversation arrives live with its unread; opening it reads it and shows the thread;
// the composer says nothing can be sent while the number is not connected, with the reason's code, and
// opens when erplora.com reports it connected; a reply is kept and handed to the run's real erplora.com, where
// erplora.com's own test seed gave `a` a number (whatsapp-helpers.ts, `seedErplora`): erplora.com takes it to Meta,
// which refuses the seed's made-up permission, and the bubble says «Not delivered» with that reason, never «Sent»
// (Meta's statuses through erplora.com: whatsapp-inbox-erplora.spec.ts); a template with its variable, handed over
// the same way; a note, «Pending», «Assign to me»,
// «Create card» joining a Customers card; «Erase this number's data» asked first. An attachment, the
// echo of the owner's phone and an option tapped show in the thread; the filters keep who waits; the
// month spent and a number to reconnect are said and go by themselves. An employee notes and takes a
// conversation but neither erases nor opens Settings. Each flow's screen in three sizes
// (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440). What it creates is deleted after the file.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp as cleanUpCards } from './customer-helpers';
import { A, EMPLOYEE, hostPage, login, SAAS, shot, shown } from './helpers';
import { cleanUp, e2ePhone, flowShots, PREFIX, pushChannel, receive, seedErplora, template, waId } from './whatsapp-helpers';

test.beforeAll(() => {
  // erplora.com takes `a`'s number (its test seed): what the Hub hands it reaches Meta.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
});

test.afterAll(() => {
  cleanUp();
  cleanUpCards();
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

/** Picks `option` in the inbox's column filter `filter` (beside the search at this width). */
async function filterInbox(page: Page, filter: string, option: string): Promise<void> {
  await shown(page).locator(`[data-testid=whatsapp-inbox-filter-${filter}]`).click();
  await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${option}\\s*$`) }).click();
  await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
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

  // F32: the reply is kept and handed to erplora.com (door 5), which takes it to Meta: Meta refuses the seed's
  // made-up permission and erplora.com says so (409), so the bubble says «Not delivered» with that reason and offers
  // no «Retry» (the same key would get the same answer); never «Sent» without Meta's id.
  const text = panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea');
  await expect(text).toBeEnabled();
  await text.fill('Sí, a las 17:00 tenemos hueco.');
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-send]').click();
  const reply = bubbles(page, 'outbound').filter({ hasText: 'a las 17:00 tenemos hueco' });
  await expect(reply).toBeVisible();
  await expect(text).toHaveValue('');
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
  await expect(reply.locator('.wa-bubble__error')).toContainText("Meta's reason:");
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-retry]')).toHaveCount(0);
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
  // Handed to erplora.com (door 5) like a reply: Meta refuses the seed's permission, «Not delivered» with the reason.
  const sentTemplate = bubbles(page, 'outbound').filter({ hasText: 'e2e_recordatorio' });
  await expect(sentTemplate).toBeVisible();
  await expect(sentTemplate.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
  await expect(sentTemplate.locator('.wa-bubble__error')).toContainText("Meta's reason:");

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

  // F06: a photo she sends opens at erplora.com in a new tab, named by its kind, with its caption.
  receive(phone, '', name, {
    type: 'image',
    media: { url: `${SAAS}/whatsapp/media/${PREFIX}foto.jpg`, mime_type: 'image/jpeg', filename: '', caption: 'Así lo quiero' },
  });
  const media = panel(page).locator('[data-testid=whatsapp-inbox-message-media]');
  await expect(media).toContainText('Photo');
  await expect(media).toContainText('Así lo quiero');
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

// WHATSAPP_INBOX-F32, F34: a reply that really leaves through erplora.com shows «Sending…», then «Sent»
// with Meta's id and the statuses Meta reports. The Hub's side is mounted (`/internal/whatsapp/status`
// since hub#127); erplora.com's door `/internal/whatsapp/send` does not exist yet: marked, never simulated.
test.fixme('a reply really leaves through erplora.com and Meta’s statuses arrive', async () => {});
