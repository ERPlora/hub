// flow: HUB_APP-F04 (ERPlora/app, workflow/instalar-y-enlazar.md) · BASE-F61
// «Change business» exists only inside the installed app: a browser has no business to forget, and its bar never
// offers it, at any size. Inside the app (its bridge stood in by the test, which keeps what the hub asks of it, as
// print-in-the-app.spec.ts does), the bar offers it (a row of «⋮» on a phone), «Change business?» asks, and confirming
// closes this business's session on the real Hub, erases what the hub kept in this browser but the device's own, and
// only then asks the app to forget the hub, with the list of businesses forced.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, shown, THREE_SIZES } from './helpers';
import { compactBar, topbar, topbarMore, topbarMoreMenu } from './topbar';

const KEY = 'HUB-1649-change-business';
const BUTTON = '[data-testid=change-business-button]';
/** The device's own keys, which survive: its id (spa-config's `deviceIdStorageKey`) and its answer about the notices. */
const PRIMER_ANSWERED_KEY = 'erplora.notifications.primerAnswered';

interface Asked {
  command: string;
  args: unknown;
  local: string[];
  session: string[];
}

/** The app's bridge in every page of `context`: `forget_hub` is kept with what the browser still held at that moment;
 *  any other command is refused, as an app without it would. */
async function appBridge(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const asked: Asked[] = [];
    (window as unknown as { asked: Asked[] }).asked = asked;
    const invoke = (command: string, args?: unknown) => {
      if (command !== 'forget_hub') return Promise.reject('unknown_command');
      asked.push({ command, args, local: Object.keys(localStorage).sort(), session: Object.keys(sessionStorage).sort() });
      return Promise.resolve(null);
    };
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke } };
  });
}

const askedOf = (page: Page): Promise<Asked[]> => page.evaluate(() => (window as unknown as { asked: Asked[] }).asked);

/** The Home loaded at `size`, with the hub's piece of the bar painted (the assistant's sparkles: on a phone, «⋮»). */
async function homeAt(page: Page, size: (typeof THREE_SIZES)[number]): Promise<void> {
  await page.setViewportSize({ width: size.width, height: size.height });
  await page.goto(`${A}/`);
  await expect(shown(page).locator('[data-testid="setup-progress"]')).toBeVisible();
  if (compactBar(page)) await expect(topbarMore(page)).toBeVisible();
  else await expect(topbar(page).locator('[data-testid=assistant-button]')).toBeVisible();
}

/** Opens «⋮» on a phone: the hub's piece is listed in it. */
async function openMore(page: Page): Promise<void> {
  await topbarMore(page).click();
  await expect(topbarMoreMenu(page).locator('[data-testid=assistant-button]')).toBeVisible();
}

test('in a browser the bar never offers «Change business», at any size', async ({ page }) => {
  await login(page, A, '/');
  for (const size of THREE_SIZES) {
    await homeAt(page, size);
    if (compactBar(page)) await openMore(page);
    await expect(page.locator(BUTTON), `no «Change business» at ${size.label}`).toHaveCount(0);
  }
});

test('inside the app, «Change business» asks, signs out of this business and only then asks the app to forget it', async ({ page }) => {
  await appBridge(page.context());
  await login(page, A, '/');
  for (const size of THREE_SIZES) {
    await homeAt(page, size);
    if (compactBar(page)) await openMore(page);
    const button = compactBar(page) ? topbarMoreMenu(page).locator(BUTTON) : topbar(page).locator(BUTTON);
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute('aria-label', 'Change business');
    await capture(page, `${KEY}-bar-${size.label}`);
    await button.click();
    const dialog = page.locator('[data-testid=change-business-dialog]');
    await expect(dialog).toContainText('Change business?');
    await expect(dialog).toContainText('You will be signed out of this business and see the list of your businesses to choose another.');
    await capture(page, `${KEY}-dialog-${size.label}`);
    await page.locator('[data-testid=change-business-dialog-cancel]').click();
    await expect(page.locator('[data-testid=change-business-dialog-submit]')).toHaveCount(0);
  }
  expect(await askedOf(page), 'cancelled, the app was asked nothing').toEqual([]);

  // What the hub kept in this browser before: the device's id and some of its own (the apps used, a switch's name).
  const deviceKey = await page.evaluate(() => {
    const config = JSON.parse(document.getElementById('spa-config')?.textContent ?? '{}') as { deviceIdStorageKey?: string };
    localStorage.setItem('hub-app-usage', '{"sale":3}');
    sessionStorage.setItem('erplora.base.switched', 'Ana');
    return config.deviceIdStorageKey ?? 'erplora.device_id';
  });
  expect(await page.evaluate((key) => localStorage.getItem(key), deviceKey)).not.toBeNull();

  const order: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/auth/logout') order.push('sign-out');
  });
  if (compactBar(page)) await openMore(page);
  await (compactBar(page) ? topbarMoreMenu(page) : topbar(page)).locator(BUTTON).click();
  await page.locator('[data-testid=change-business-dialog-submit]').click();
  await expect.poll(async () => (await askedOf(page)).length).toBe(1);

  const [forget] = await askedOf(page);
  expect(order, 'the sign-out went before the app was asked').toEqual(['sign-out']);
  expect(forget.command).toBe('forget_hub');
  expect(forget.args).toEqual({ choose: true });
  expect(forget.local.filter((key) => key !== deviceKey && key !== PRIMER_ANSWERED_KEY)).toEqual([]);
  expect(forget.local).toContain(deviceKey);
  expect(forget.session).toEqual([]);
  // The business's session is over: its API knows nobody in this browser.
  expect((await api<{ user: unknown }>(page.context(), A, 'GET', '/me')).data.user).toBeNull();
});
