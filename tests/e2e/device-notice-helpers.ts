// The installed app's notification bridge and the checks every device's notices share. Tauri does not
// run in Playwright: only this edge is simulated; the Hub, SaaS, live stream and database stay real.
import { expect, type Page } from '@playwright/test';

/**
 * Every native command is recorded; the notification tap listener, the app's «a tap waits» listeners, the tap the
 * app keeps for the page and the device's memory are kept.
 */
export function nativeApp(): void {
  const win = window as unknown as Record<string, unknown>;
  win.__asked = [];
  win.__told = 0;
  win.__kept = null;
  win.__waits = [];
  const setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key: string, value: string) {
    if (key === 'erplora.notices.told') win.__told = (win.__told as number) + 1;
    return setItem.call(this, key, value);
  };
  win.__TAURI__ = {
    core: {
      invoke: async (command: string, args?: unknown) => {
        (win.__asked as unknown[]).push([command, args ?? null]);
        if (command !== 'erplora_take_notice_tap') return null;
        // The kept tap is handed over once, like the app's `take_notice_tap`.
        const kept = win.__kept;
        win.__kept = null;
        return kept;
      },
      // The `notification` plugin's report of a tap; the shell also holds the `app` plugin's Back button (BASE-F05).
      addPluginListener: async (plugin: string, _event: string, cb: (payload: unknown) => void) => {
        if (plugin === 'notification') win.__tap = cb;
        return { unregister: async () => {} };
      },
    },
    event: {
      // The app's event that a tap waits to be claimed (`erplora://notice-tapped`).
      listen: async (event: string, cb: () => void) => {
        if (event === 'erplora://notice-tapped') (win.__waits as (() => void)[]).push(cb);
        return () => {};
      },
    },
  };
}

export interface Notified {
  title: string;
  body: string;
  id: number;
  path: string | null;
}

export const notified = (page: Page): Promise<Notified[]> =>
  page.evaluate(() =>
    ((window as unknown as { __asked: [string, unknown][] }).__asked ?? [])
      .filter(([command]) => command === 'erplora_notify')
      .map(([, args]) => args as Notified),
  );

const toldWrites = (page: Page): Promise<number> =>
  page.evaluate(() => (window as unknown as { __told: number }).__told);

/** The installed app from this reload: its first read only learns what is already there. */
export async function startDeviceNotices(page: Page): Promise<void> {
  await page.reload();
  await expect(page.locator('[data-testid=device-notices]')).toBeAttached();
  await expect.poll(() => toldWrites(page)).toBeGreaterThan(0);
  expect(await notified(page)).toEqual([]);
}

/** A reload brings the last 24 hours back, but this device has told them already. */
export async function expectNoRepeatOnReload(page: Page): Promise<void> {
  await page.reload();
  await expect.poll(() => toldWrites(page)).toBeGreaterThan(0);
  expect(await notified(page)).toEqual([]);
}

/**
 * A tap on notice `id`, as the Android app delivers it (hub#1039): the `notification` plugin's own report says
 * neither the number nor the screen (it never stores the notice on the tap), so the app keeps the tap with the
 * screen it wrote down when the notice went out and tells the page one waits; the page claims it.
 */
export async function tapNotification(page: Page, id: number): Promise<void> {
  await page.evaluate((notificationId) => {
    const win = window as unknown as {
      __tap?: (payload: unknown) => void;
      __asked: [string, unknown][];
      __kept: unknown;
      __waits: (() => void)[];
    };
    win.__tap?.({ actionId: 'tap' });
    const sent = win.__asked.find(
      ([command, args]) => command === 'erplora_notify' && (args as { id?: unknown }).id === notificationId,
    );
    const path = (sent?.[1] as { path?: string | null } | undefined)?.path ?? null;
    win.__kept = { notification: { id: notificationId, extra: { path } } };
    win.__waits.forEach((wait) => wait());
  }, id);
}
