// flow: BASE-F113 (base/WORKBOOK.md) · HUB_APP-F26 (ERPlora/app)
// hub#836: inside the installed app, a person signed in who hears something (a new kitchen ticket) with the notices
// allowed asks the app to stay listening with the screen off, in the person's language; «Sign out» stops it before the
// page leaves. An app without the command (the 1.1.34) is asked once and the page goes on as before, with nothing on
// screen. Tauri is simulated only at the native bridge; the Hub, SaaS, live stream and database are real.
import { expect, type Page, test } from '@playwright/test';

import { nativeApp, type NativeAppOptions } from './device-notice-helpers';
import { A, api } from './helpers';
import { ownerPage } from './service-helpers';

const KEEP_LISTENING = 'plugin:erplora-android|keep_listening';

type Call = [command: string, args: unknown];

/** The native commands the page asks, kept outside it so they outlive a sign-out. */
async function asTheApp(page: Page, options: NativeAppOptions): Promise<Call[]> {
  const calls: Call[] = [];
  await page.exposeFunction('__nativeCall', (command: string, args: unknown) => void calls.push([command, args]));
  await page.context().addInitScript(nativeApp, options);
  await page.reload();
  await expect(page.locator('[data-testid=device-notices]')).toBeAttached();
  return calls;
}

const listened = (calls: Call[]) => calls.filter(([command]) => command === KEEP_LISTENING).map(([, args]) => args);

/** «Sign out» of the user menu (the side menu pinned at 1440); done once the page has left the business. */
async function signOut(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('ion-menu [data-testid="user-menu-trigger"]').click();
  await page.locator('ion-popover [data-testid="user-menu-logout"]').click();
  await page.waitForURL((url) => !url.href.startsWith(A));
}

test('signed in with a kitchen to hear, the app stays listening with the screen off; «Sign out» stops it before leaving', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/');
  try {
    const notices = await api<{ sources: string[] }>(context, A, 'GET', '/home/notices');
    expect(notices.status).toBe(200);
    expect(notices.data.sources).toContain('kitchen.received');

    const calls = await asTheApp(page, { notices: true });

    await expect
      .poll(() => listened(calls))
      .toEqual([
        {
          on: true,
          title: 'ERPlora is listening',
          body: "You'll be warned when something needs your attention, even with the screen off.",
          channel: 'Notices with the screen off',
        },
      ]);
    await signOut(page);
    expect(listened(calls)).toEqual([expect.objectContaining({ on: true }), { on: false }]);
  } finally {
    await context.close();
  }
});

test('«Not now» to our sentence, with Android not letting the app notify: the app is never kept awake', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/');
  try {
    const calls = await asTheApp(page, { notices: false });
    await page.locator('ion-alert button', { hasText: 'Not now' }).click();

    await expect.poll(() => listened(calls)).toEqual([{ on: false }]);
    expect(calls.map(([command]) => command)).not.toContain('plugin:erplora-android|request_permissions');
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  } finally {
    await context.close();
  }
});

test('an app without the command (the 1.1.34) is asked once: nothing on screen, no error, and «Sign out» still leaves', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  try {
    const calls = await asTheApp(page, { notices: true, withoutKeepListening: true });

    await expect.poll(() => listened(calls)).toHaveLength(1);
    await expect(page.locator('ion-toast')).toHaveCount(0);
    await expect(page.locator('ion-alert')).toHaveCount(0);
    await signOut(page);
    expect(listened(calls)).toHaveLength(1);
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
