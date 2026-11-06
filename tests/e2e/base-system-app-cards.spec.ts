// System › «Usage and plan» has, at its end, the cards the apps on put there (hub#683; BASE-F39 step 5, PRINTING-F21;
// the old hub's «Your printer» of «Resources», HUB_SHELL-F137/F138), as the owner of hub `a` and in the three viewports
// of the fleet: with Printing on, «Your printer» says who prints, «Set up printing» leads to Printing's printers and,
// in this browser, the ERPlora app for Windows, Linux and Android comes from erplora.com (the stack's SaaS), each
// opening outside the hub. Printing turned off takes the card away without a reload and turned on brings it back. The
// employee, who is told the business's usage is not theirs, still has the card; in Spanish, «Tu impresora». Each step
// leaves its capture `hub683-<step>-<width>` once nothing scrolls sideways; Printing ends as the run found it.
// flow: BASE-F39 PRINTING-F21
import { type Browser, expect, type Page, test } from '@playwright/test';

import {
  A,
  api,
  EMPLOYEE,
  hostPage,
  saveSessionForTheSweep,
  settledCapture,
  signedInSpanish,
  testid,
  turnOffTurnedOn,
  turnOnMissing,
} from './helpers';
import { STACK } from './stack';

const VIEWPORTS = {
  1440: { width: 1440, height: 900 },
  820: { width: 820, height: 1180 },
  375: { width: 375, height: 667 },
} as const;

const card = (page: Page) => testid(page, 'printing-system-card');
const download = (page: Page, platform: string) => testid(page, `printing-system-card-download-${platform}`);

async function owner(browser: Browser, viewport: { width: number; height: number }) {
  return hostPage(browser, A, { viewport, next: '/system' });
}

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F39 PRINTING-F21 — «Your printer» in System at ${width}`, async ({ browser }) => {
    const { context, page } = await owner(browser, viewport);
    const turnedOn: string[] = [];
    try {
      await turnOnMissing(context, A, ['printing'], turnedOn);
      await page.reload();
      await saveSessionForTheSweep(context);

      // The card, below what the business uses: who prints, and the way to Printing.
      await expect(testid(page, 'tab-usage')).toHaveClass(/segment-button-checked/);
      await expect(testid(page, 'printing-system-card-title')).toHaveText('Your printer');
      await expect(testid(page, 'printing-system-card-intro')).toHaveText(
        'Receipts, kitchen orders and labels are printed by the ERPlora app on the device next to the printer.',
      );
      // In a browser, the ERPlora app of each system erplora.com publishes, its door on the stack's SaaS, in a new tab.
      for (const platform of ['windows', 'linux', 'android']) {
        await expect(download(page, platform)).toHaveJSProperty('href', `${STACK.saas}/app/download/${platform}/`);
        await expect(download(page, platform)).toHaveJSProperty('target', '_blank');
      }
      await expect(testid(page, 'printing-system-card-download-title')).toHaveText('Download the ERPlora app');
      await card(page).scrollIntoViewIfNeeded();
      await settledCapture(page, `hub683-card-${width}`);

      // Turned off, the card goes without a reload; turned on, it comes back.
      const off = await api(context, A, 'POST', '/apps/disable', { app: 'printing' });
      expect(off.status, JSON.stringify(off.data)).toBe(200);
      await expect(card(page)).toHaveCount(0);
      await settledCapture(page, `hub683-printing-off-${width}`);
      await turnOnMissing(context, A, ['printing'], []);
      await expect(testid(page, 'printing-system-card-title')).toHaveText('Your printer');

      // «Set up printing» opens Printing's printers.
      await testid(page, 'printing-system-card-setup').click();
      await expect(page).toHaveURL(`${A}/printing/printers`);
    } finally {
      // A run that falls between «off» and «on» still leaves Printing as it found it: the employee's and the Spanish
      // tests below, and every spec after this file, count on it being on in `a`.
      if (turnedOn.length === 0) await turnOnMissing(context, A, ['printing'], []);
      await turnOffTurnedOn(context, A, turnedOn);
      await context.close();
    }
  });
}

test('BASE-F39 PRINTING-F21 — the employee has the card too, below what is not theirs to see', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { viewport: VIEWPORTS[375], next: '/system', credentials: EMPLOYEE });
  try {
    await expect(testid(page, 'system-usage-denied')).toHaveText(
      'Only the owner or an administrator can see how much the hub is using.',
    );
    await expect(testid(page, 'printing-system-card-title')).toHaveText('Your printer');
    await card(page).scrollIntoViewIfNeeded();
    await settledCapture(page, 'hub683-employee-375');
  } finally {
    await context.close();
  }
});

test('BASE-F39 PRINTING-F21 — in Spanish, «Tu impresora»', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, VIEWPORTS[1440], '/system');
  try {
    await expect(testid(page, 'printing-system-card-title')).toHaveText('Tu impresora');
    await expect(testid(page, 'printing-system-card-setup')).toHaveText('Configurar la impresión');
    await expect(testid(page, 'printing-system-card-download-title')).toHaveText('Descargar la app de ERPlora');
    await card(page).scrollIntoViewIfNeeded();
    await settledCapture(page, 'hub683-es-1440');
  } finally {
    await context.close();
  }
});
