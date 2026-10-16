// The WhatsApp inbox in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the owner of hub `a` opens
// the inbox with the number not connected and reads why; a customer writes (erplora.com's push, run as
// the system) and her conversation arrives live with its unread; opening it reads it and shows the thread;
// the composer says nothing can be sent while the number is not connected, with the reason's code, and
// opens when erplora.com reports it connected; a note, «Pending», «Assign to me», the approved templates,
// «Create card» joining a Customers card; Settings with the number, the month and the Meta templates;
// «Erase this number's data» asked first. An employee notes and takes a conversation but neither erases
// nor opens Settings. Screens in three viewports. What it creates is deleted after the file.
// A reply that really leaves waits for erplora.com's sending door (`/internal/whatsapp/send`, WORKBOOK
// «Contrato con el SaaS»): that test is marked `fixme` and never simulated.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cleanUp as cleanUpCards } from './customer-helpers';
import { A, EMPLOYEE, hostPage, login, SAAS, shot, shown } from './helpers';
import { cleanUp, e2ePhone, PREFIX, pushChannel, receive, template } from './whatsapp-helpers';

test.afterAll(() => {
  cleanUp();
  cleanUpCards();
});

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

const rowOf = (page: Page, phone: string) => shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone });
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');

async function searchInbox(page: Page, text: string): Promise<void> {
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(text);
}

test('the owner reads, organises and erases a WhatsApp conversation; the composer follows the number', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Ana ${Date.now().toString(36)}`;
  pushChannel({ status: 'not_connected' });

  await login(page, A, '/whatsapp_inbox/inbox');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toContainText('WhatsApp is not connected');
  // The run's SaaS (`SAAS_URL`: :8001 on the shared stack, its own beside it; erplora.com in production).
  const saas = new RegExp(`^${SAAS.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(/|$)`);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-go-to-saas]')).toHaveAttribute('href', saas);
  await searchInbox(page, phone.slice(3));

  // F03: the customer writes; her conversation arrives live, unread.
  receive(phone, 'Hola, ¿tenéis hora mañana por la tarde?', name);
  await expect(rowOf(page, phone)).toBeVisible();
  await expect(rowOf(page, phone)).toContainText(name);
  await expect(rowOf(page, phone).locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');

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

  // erplora.com reports the number connected, with its templates: the composer opens by itself.
  pushChannel({
    status: 'connected',
    templates: [template('e2e_recordatorio'), template('e2e_rechazada', { status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' })],
  });
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toBeHidden();
  await expect(blocked).toBeHidden();
  const text = panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea');
  await expect(text).toBeEnabled();
  await text.fill('Sí, a las 17:00 tenemos hueco.');
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', false);
  // Sending it really is the next test's, once erplora.com's door exists: nothing is pressed here.
  await text.fill('');

  // F33: «Template» offers only the approved ones.
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-template]').click();
  const templates = page.locator('ion-modal[data-testid=whatsapp-inbox-template-form]');
  await expect(templates).toContainText('e2e_recordatorio');
  await expect(templates).not.toContainText('e2e_rechazada');
  await templates.locator('[data-testid=whatsapp-inbox-template-form-cancel]').click();
  await expect(templates).toBeHidden();

  // F36: an internal note, in the thread.
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-mode-note]').click();
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-note] textarea').fill('Prefiere las tardes.');
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-add-note]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-note]')).toContainText('Prefiere las tardes.');

  // F35 and F07: «Pending» and «Assign to me», on the panel and on the row.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-status-pending]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Pending');
  await expect(rowOf(page, phone)).toContainText('Pending');
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-assign-me]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-assign-me]')).toBeHidden();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-unassign]')).toBeVisible();

  // F37: «Create card» makes a Customers card with her WhatsApp name and number, and joins it.
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-create-card]').click();
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-customer]')).toHaveText(name);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-view-card]')).toHaveAttribute('href', /\/customer\/customers\//);

  // The customer writes again while the thread is open: it shows, the conversation reopens, it stays read.
  receive(phone, '¡Genial, gracias!', name);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-message][data-side=inbound]')).toHaveCount(2);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-detail-status]')).toContainText('Open');

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await expect(panel(page)).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${viewport.label}` })
      .toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`whatsapp-inbox-conversation-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });

  // Settings: the number, the month and the Meta templates with Meta's reason.
  await shown(page).locator('[data-testid=tab-settings]').click();
  await page.waitForURL(/\/whatsapp_inbox\/settings$/);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-number]')).toContainText('+34910000000');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-month]')).toContainText('12 of 150 messages sent');
  await shown(page).locator('[data-testid=whatsapp-inbox-templates-search] input').fill('e2e_');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-templates-row]', { hasText: 'e2e_rechazada' })).toContainText('INVALID_FORMAT');
  await page.screenshot({ path: shot('whatsapp-inbox-settings-1280') });

  // F10: «Erase this number's data» asks first, naming the number; erased, it leaves the inbox.
  await shown(page).locator('[data-testid=tab-inbox]').click();
  await page.waitForURL(/\/whatsapp_inbox\/inbox/);
  await searchInbox(page, phone.slice(3));
  await rowOf(page, phone).click();
  await panel(page).locator('[data-testid=whatsapp-inbox-detail-erase]').click();
  const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: "Erase this number's data?" });
  await expect(confirm).toContainText(phone);
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-erased]')).toContainText('The data of this number has been erased.');
  await expect(rowOf(page, phone)).toHaveCount(0);
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

// WHATSAPP_INBOX-F32, F34: a reply leaves through erplora.com, shows «Sending…», then «Sent» and its later
// statuses. It needs erplora.com's door `/internal/whatsapp/send` (and `base`'s `/internal/whatsapp/status`),
// which do not exist yet: marked, never simulated.
test.fixme('a reply leaves through erplora.com and its delivery statuses arrive', async () => {});
