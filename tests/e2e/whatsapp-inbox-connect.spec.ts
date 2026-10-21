// flow: WHATSAPP_INBOX-F01, WHATSAPP_INBOX-F02
// Connecting and disconnecting the business's WhatsApp number from the inbox's Settings, in a hidden Chrome, against
// the run's real erplora.com (`SAAS_URL`) and its doors 10–12 (WORKBOOK «Contrato con el SaaS»). Neither erplora.com
// nor the Hub is a double; what erplora.com's photo says of the number (connected, not connected) is pushed as the
// system, as its door 4 does (whatsapp-helpers.ts), because the run's erplora.com knows the local hub `a` by another id.
//
// F01: the owner of `a` opens Settings with the number not connected; the Hub asks erplora.com what opens Meta's
// window (door 10) and, as erplora.com has no page yet to bring Meta's one-time code back (FIX in the SaaS), says it
// cannot be connected from here yet and offers nothing to press; the inbox's notice leads to Settings. Meta's window
// itself (lib/metaSignup.ts, composables/useMetaSignup.ts) is proven in Vitest: it cannot open here until erplora.com
// serves that page and the Hub keeps the windows it opens (COOP, FIX in `base`).
// F02: the number reported connected is disconnected from Settings, asked first; erplora.com (door 12) answers it had
// no number for `a`, and «Your number» says «Not connected» at once, without reloading.
// Each in three sizes (FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12[-F02]-390|834|1440). What it creates is deleted.
import { expect, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, pushChannel } from './whatsapp-helpers';

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

test('WHATSAPP_INBOX-F01: Settings asks erplora.com what opens Meta’s window and says why it cannot open yet', async ({ page }) => {
  pushChannel({ status: 'not_connected' });
  const asked = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/prepare'));
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-go-to-settings]').click();
  await expect(page).toHaveURL(/\/whatsapp_inbox\/settings$/);

  // erplora.com answered (200): the window is not offered, and the screen says why, in the user's words.
  expect((await asked).status()).toBe(200);
  await expect(number(page)).toContainText('Not connected');
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-unavailable]')).toHaveText(
    /^(Connecting the number from here is not available yet\.|WhatsApp is not available in ERPlora yet\.)$/,
  );
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-connect]')).toHaveCount(0);
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-disconnect]')).toHaveCount(0);
  await shots(page, TASK, async (p) => {
    await expect(number(p).locator('[data-testid=whatsapp-inbox-number-unavailable]')).toBeVisible();
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

  // erplora.com (door 12) keeps no number for the local hub `a`: it says so, and the Hub stops believing it has one.
  const answer = await told;
  expect(answer.status()).toBe(200);
  expect(await answer.json()).toEqual({ disconnected: false });
  await expect(dialog).toBeHidden();
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-done]')).toHaveText(
    'erplora.com had no number connected for this business.',
  );
  await expect(number(page)).toContainText('Not connected');
  await expect(number(page)).not.toContainText('+34910000000');
});
