// flow: BASE-F120 (base/WORKBOOK.md) · HUB_APP-F27 (ERPlora/app, workflow/salidas-y-actualizacion.md)
// «Start on login» lives in «This device» of Settings › General, only in the computer app. In a browser it is not
// there; inside the app (its bridge stood in by the test, which keeps the operating system's answer, as
// base-change-business.spec.ts does) it starts off, turning it on asks the app and shows what the system says, and a
// refusal says it could not change and leaves the switch where the system is. Each state at the three sizes.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, login, OWNER, shown } from './helpers';

const KEY = 'BASE-F120-autostart';
const ROW = '[data-testid="device-mode-card"] [data-testid="device-autostart"]';
const TOGGLE = '[data-testid="device-autostart-toggle"]';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

interface System {
  enabled: boolean;
  refuse: boolean;
  asked: string[];
}

/** The computer app's bridge in every page of `context`, its system off: the autostart commands answer what it says
 *  (`refuse` makes a change fail); any other command is refused, as an app without it would. */
async function computerApp(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const system: System = { enabled: false, refuse: false, asked: [] };
    (window as unknown as { system: System }).system = system;
    const invoke = (command: string) => {
      system.asked.push(command);
      if (command === 'autostart_is_enabled') return Promise.resolve(system.enabled);
      if (command !== 'autostart_enable' && command !== 'autostart_disable') return Promise.reject('unknown_command');
      if (system.refuse) return Promise.reject('Access is denied.');
      system.enabled = command === 'autostart_enable';
      return Promise.resolve(system.enabled);
    };
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke } };
  });
}

const systemOf = (page: Page): Promise<System> => page.evaluate(() => (window as unknown as { system: System }).system);

async function settingsAt(page: Page, size: (typeof SIZES)[number]): Promise<void> {
  await page.setViewportSize(size);
  await page.goto(`${A}/settings`);
  // The whole tab loaded, so a capture shows the card as a person sees it.
  await expect(shown(page).getByTestId('device-mode')).toBeVisible();
  await expect(shown(page).getByTestId('pin-policy-show')).toBeVisible();
  await expect(shown(page).getByTestId('devices-card')).not.toContainText('Loading the devices');
}

const label = (size: (typeof SIZES)[number]) => `${size.width}x${size.height}`;

test('in a browser Settings has no «Start on login», at any size', async ({ page }) => {
  await login(page, A, '/settings');
  for (const size of SIZES) {
    await settingsAt(page, size);
    await expect(page.locator(ROW), `none at ${label(size)}`).toHaveCount(0);
  }
});

test('inside the computer app it starts off, turns on with the system and says when it could not change', async ({ page }) => {
  await computerApp(page.context());
  // A fresh entry, so this computer is a device of the business, as it is after signing in on it.
  await login(page, A, '/settings', OWNER, { fresh: true });
  for (const size of SIZES) {
    await settingsAt(page, size);
    const row = shown(page).locator(ROW);
    await expect(row).toContainText('Open ERPlora when you sign in to this computer, so tickets always have somewhere to print.');
    await expect(row.locator(TOGGLE)).toHaveText('Start on login');
    await expect(row.locator(TOGGLE)).toHaveJSProperty('checked', false);
    await row.scrollIntoViewIfNeeded();
    await capture(page, `${KEY}-off-${label(size)}`);
  }

  const row = shown(page).locator(ROW);
  await row.locator(TOGGLE).click();
  await expect(row.locator(TOGGLE)).toHaveJSProperty('checked', true);
  expect((await systemOf(page)).enabled).toBe(true);
  expect((await systemOf(page)).asked.filter((command) => command.startsWith('autostart'))).toEqual(['autostart_is_enabled', 'autostart_enable']);

  await page.evaluate(() => ((window as unknown as { system: System }).system.refuse = true));
  await row.locator(TOGGLE).click();
  await expect(row.getByTestId('device-autostart-error')).toContainText('Could not change the start on login setting.');
  await expect(row.locator(TOGGLE)).toHaveJSProperty('checked', true);
  await expect(row.locator(TOGGLE)).toHaveJSProperty('disabled', false);
  for (const size of [...SIZES].reverse()) {
    await page.setViewportSize(size);
    await row.scrollIntoViewIfNeeded();
    await capture(page, `${KEY}-refused-${label(size)}`);
  }
});
