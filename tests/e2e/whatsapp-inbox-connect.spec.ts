// flow: WHATSAPP_INBOX-F01, WHATSAPP_INBOX-F02
// Connecting and disconnecting the business's WhatsApp number from the inbox's Settings, in a hidden Chrome, against
// the run's real erplora.com (`SAAS_URL`) and its doors 10–12 (WORKBOOK «Contrato con el SaaS»). Neither erplora.com
// nor the Hub is a double; what erplora.com's photo says of the number (connected, not connected) is pushed as the
// system, as its door 4 does (whatsapp-helpers.ts), because the run's erplora.com knows the local hub `a` by another id.
//
// F01: the owner of `a` opens Settings with the number not connected; the Hub asks erplora.com what opens Meta's
// window (door 10) and, with erplora.com's own return page (plain http in development, its SAAS_URL's origin),
// offers «Connect WhatsApp»; the inbox's notice leads to Settings. Pressing it, Meta's window and erplora.com's return
// page bringing the code back are whatsapp-inbox-connect-return.spec.ts.
// F02: erplora.com's own test seed gives `a` its number there (whatsapp-helpers.ts, `seedErplora`); disconnecting it from
// Settings, asked first, has erplora.com (door 12) disconnect it, and «Your number» says «Not connected» at once,
// without reloading.
// Each in three sizes (FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12[-F02]-390|834|1440). What it creates is deleted.
import { expect, type Page, test } from '@playwright/test';

import { A, login, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, pushChannel, seedErplora } from './whatsapp-helpers';

test.beforeAll(() => {
  // erplora.com takes `a`'s number (its test seed) and this Hub takes its photo.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
});

test.afterAll(() => cleanUp());

const TASK = 'FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12';
const number = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-number]');

async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('WHATSAPP_INBOX-F01: Settings asks erplora.com what opens Meta’s window and offers «Connect WhatsApp»', async ({ page }) => {
  pushChannel({ status: 'not_connected' });
  const asked = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/prepare'));
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-go-to-settings]').click();
  await expect(page).toHaveURL(/\/whatsapp_inbox\/settings$/);

  // erplora.com answered (200) with its return page: the window is offered, and nothing says it cannot open.
  const answer = await asked;
  expect(answer.status()).toBe(200);
  expect(await answer.json()).toMatchObject({ available: true, reason: null, redirect_uri: `${SAAS}/whatsapp/return` });
  await expect(number(page)).toContainText('Not connected');
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-connect]')).toHaveText('Connect WhatsApp');
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-unavailable]')).toHaveCount(0);
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-disconnect]')).toHaveCount(0);
  await shots(page, TASK, async (p) => {
    await expect(number(p).locator('[data-testid=whatsapp-inbox-number-connect]')).toBeVisible();
  });
});

test('WHATSAPP_INBOX-F02: the number is disconnected from Settings through erplora.com, asked first', async ({ page }) => {
  pushChannel({ status: 'connected' });
  await login(page, A, '/whatsapp_inbox/settings');
  await expect(number(page)).toContainText('Connected');
  await expect(number(page)).toContainText('+34910000000');
  await shots(page, `${TASK}-F02`, async (p) => {
    await expect(number(p).locator('[data-testid=whatsapp-inbox-number-disconnect]')).toBeVisible();
  });

  await number(page).locator('[data-testid=whatsapp-inbox-number-disconnect]').click();
  const dialog = page.locator('[data-testid=whatsapp-inbox-number-disconnect-dialog]');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('+34910000000');
  await expect(dialog).toContainText('The conversations kept stay.');
  const told = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/disconnect'));
  await page.locator('[data-testid=whatsapp-inbox-number-disconnect-dialog-submit]').click();

  // erplora.com (door 12) disconnects the number its seed gave `a`, and the Hub stops having one at once.
  const answer = await told;
  expect(answer.status()).toBe(200);
  expect(await answer.json()).toEqual({ disconnected: true });
  await expect(dialog).toBeHidden();
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-done]')).toHaveText('WhatsApp disconnected.');
  await expect(number(page)).toContainText('Not connected');
  await expect(number(page)).not.toContainText('+34910000000');
});
