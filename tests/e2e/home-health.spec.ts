// flow: BASE-F02 PRINTING-F21
// The Home's health row, under the greeting: the owner of `a`, in Spanish, sees how the receipt printer and the WhatsApp
// number are working, goes to connect WhatsApp from its action and, back on the Home, the row says it is connected
// without a reload. «Ver sistema» opens System, whose «Tu impresora» says the same state of the printer. An employee has
// no row and her Home never asks for it. In the three sizes, with the captures `<KEY>-<label>`. erplora.com's pushes of
// the number run as its door does (whatsapp-helpers.ts); `a`'s photo is kept first and put back last.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, hostPage, saveSessionForTheSweep, shown, THREE_SIZES, turnOffTurnedOn, turnOnMissing } from './helpers';
import { spanishContext, spanishHome } from './home-helpers';
import { capturedFitting } from './screen';
import { keepPhoto, pushChannel, restorePhoto } from './whatsapp-helpers';

const KEY = 'BASE-F02-HOME-HEALTH';
const NEEDED = ['printing', 'whatsapp_inbox'] as const;
const turnedOn: string[] = [];

/** What «Tu impresora» says of each state of the printer, the one the Home's row said. */
const PRINTER_TITLES: Record<string, string> = {
  ok: 'Impresora lista',
  no_signal: 'Impresora sin conectar',
  not_configured: 'Impresora sin configurar',
};

const row = (page: Page): Locator => shown(page).locator('[data-testid="home-health"]');
const item = (page: Page, app: string): Locator => row(page).locator(`[data-testid="home-health-item"][data-app="${app}"]`);

/** Runs `step` as the owner of `a`, in a context of its own. */
async function asTheOwner(browser: Browser, step: (context: BrowserContext) => Promise<void>): Promise<void> {
  const { context } = await hostPage(browser, A, { next: '/' });
  await step(context).finally(() => context.close());
}

test.beforeAll(async ({ browser }) => {
  keepPhoto();
  await asTheOwner(browser, (context) => turnOnMissing(context, A, NEEDED, turnedOn));
});

test.afterAll(async ({ browser }) => {
  await asTheOwner(browser, (context) => turnOffTurnedOn(context, A, turnedOn));
  restorePhoto();
});

for (const { label, width, height } of THREE_SIZES) {
  test(`BASE-F02 PRINTING-F21 — the owner sees how the printer and WhatsApp are working, and fixes WhatsApp — ${label}`, async ({
    browser,
  }) => {
    pushChannel({ status: 'reconnect_needed' });
    const context = await spanishContext(browser, { width, height });
    const page = await context.newPage();
    try {
      await spanishHome(page);
      await saveSessionForTheSweep(context);
      await expect(row(page)).toHaveAttribute('aria-busy', 'false');
      // Under the greeting, before anything else of «Resumen».
      await expect(shown(page).locator('header.home-hero + [data-testid="home-health"]')).toHaveCount(1);
      const whatsapp = item(page, 'whatsapp_inbox');
      await expect(whatsapp).toHaveAttribute('data-state', 'no_signal');
      await expect(whatsapp).toContainText('Hay que volver a conectar WhatsApp');
      const printer = item(page, 'printing');
      await expect(printer).toContainText(/Impresora (lista|sin conectar|sin configurar)/);
      const printerState = String(await printer.getAttribute('data-state'));
      await expect(row(page).locator('[data-testid="home-health-system"]')).toHaveText('Ver sistema');
      await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
      await capturedFitting(page, `${KEY}-${label}`, label);

      // «Conectar WhatsApp» opens the inbox's settings; erplora.com connects the number meanwhile.
      await whatsapp.locator('[data-testid="home-health-action"]').click();
      await expect(page).toHaveURL(`${A}/whatsapp_inbox/settings`);
      pushChannel({ status: 'connected' });

      // Back on the Home, the row is checked again: connected, with nothing to do.
      await page.goBack();
      await expect(page).toHaveURL(`${A}/`);
      await expect(whatsapp).toHaveAttribute('data-state', 'ok');
      await expect(whatsapp).toContainText('WhatsApp conectado');
      await expect(whatsapp.locator('[data-testid="home-health-action"]')).toHaveCount(0);

      // «Ver sistema» opens System, whose «Tu impresora» says what the row said of the printer.
      await row(page).locator('[data-testid="home-health-system"]').click();
      await expect(page).toHaveURL(`${A}/system`);
      const card = shown(page).locator('[data-testid="printing-system-card-state"]');
      await expect(card).toHaveAttribute('aria-busy', 'false');
      await expect(card).toContainText(PRINTER_TITLES[printerState]);
      await card.scrollIntoViewIfNeeded();
      await capturedFitting(page, `PRINTING-F21-${label}`, label);
    } finally {
      await context.close();
    }
  });
}

test('BASE-F02 — an employee has no row, and her Home never asks for it', async ({ browser }) => {
  const { width, height } = THREE_SIZES[2];
  const context = await spanishContext(browser, { width, height });
  const page = await context.newPage();
  const asked: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/home/health') asked.push(request.url());
  });
  try {
    await spanishHome(page, EMPLOYEE);
    await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
    await expect(shown(page).locator('h1')).toBeVisible();
    await expect(row(page)).toHaveCount(0);
    expect(asked).toEqual([]);
  } finally {
    await context.close();
  }
});
