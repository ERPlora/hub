// flow: ui:shell — the shell's toasts at 390, 834 and 1440 px: four in a row leave three on screen, and closing one
// makes room for the fourth; the stack sits above the screen's bottom bar; the mouse over it opens it into a list and
// stops every clock; an error stays longer than a success and carries a close button; with the assistant docked
// beside the screen, the stack is centred on the screen it shares the window with.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture } from './capture';
import { login } from './login';
import { shown, THREE_SIZES } from './screen';
import { untilStill } from './settled';
import { A } from './stack';
import { compactBar } from './topbar';
import { dismissToasts, toastSaying, toasts } from './toast-helpers';

type Tone = 'success' | 'error' | 'info' | 'warning';
interface Notice {
  message: string;
  tone: Tone;
  duration?: number;
}

/** The success's time on screen, and the error's: what the stack gives each tone when the caller says nothing. */
const SUCCESS_MS = 3000;
const ERROR_MS = 5000;

const CLOSE = /^(Close|Cerrar)$/;

/**
 * The URL of `@erplora/ui/shell` as the page's own entry imports it, read from the module Vite serves: importing that
 * same URL in the page reaches the very module the shell runs, with its stack, and not a copy of it.
 */
async function shellUrl(page: Page): Promise<string> {
  const entry = await page.locator('script[type="module"][src*="/frontend/main.ts"]').getAttribute('src');
  if (!entry) throw new Error('shellUrl(): the page has no Vite entry (is the Hub served by runserver with its Vite?)');
  const code = await (await page.request.get(new URL(entry, page.url()).href)).text();
  const specifier = /from\s*["']([^"']*(?:\/ui\/src\/shell\/index\.ts|erplora_ui_shell\.js)[^"']*)["']/.exec(code)?.[1];
  if (!specifier) throw new Error('shellUrl(): the entry does not import @erplora/ui/shell');
  return new URL(specifier, new URL(entry, page.url())).href;
}

/** Shows `notices` in this order through the shell's own `toast()`, as a screen does after its actions. */
async function show(page: Page, ...notices: Notice[]): Promise<void> {
  const url = await shellUrl(page);
  await page.evaluate(
    async ({ url, notices }) => {
      const shell = (await import(url)) as { toast: (options: Notice) => string };
      for (const notice of notices) shell.toast(notice);
    },
    { url, notices },
  );
}

const bottomStack = (page: Page): Locator => page.locator('[data-testid="toast-stack"][data-position="bottom"]');

/** The pill a person sees of a toast, without the room its element keeps around it. */
const pillOf = async (toast: Locator) => (await toast.locator('.ep-toast__body').boundingBox())!;

const messages = (page: Page): Promise<string[]> =>
  toasts(page).evaluateAll((all) => all.map((el) => el.querySelector('.ep-toast__message')?.textContent?.trim() ?? ''));

/** The Home, whose two sections sit in a bottom tabbar at every size, with the mouse away from the stack. */
async function home(page: Page, size: { width: number; height: number }): Promise<Locator> {
  await page.setViewportSize(size);
  await page.goto(`${A}/`);
  const tabbar = shown(page).locator('ion-footer.section-tabbar');
  await expect(tabbar).toBeVisible();
  await page.mouse.move(0, 0);
  return tabbar;
}

test.beforeEach(async ({ page }) => {
  await login(page, A, '/');
});

test.afterEach(async ({ page }) => {
  await page.mouse.move(0, 0);
  await dismissToasts(page);
});

test('four toasts in a row leave three on screen, newest in front, and closing one makes room for the fourth; the stack sits above the bottom bar', async ({ page }) => {
  const shownInOrder = ['First notice', 'Second notice', 'Third notice', 'Fourth notice'];
  for (const size of THREE_SIZES) {
    await test.step(size.label, async () => {
      const tabbar = await home(page, size);
      await show(page, ...shownInOrder.map((message): Notice => ({ message, tone: 'info', duration: 0 })));

      await expect(toasts(page)).toHaveCount(3);
      const order = (await messages(page)).map((message) => shownInOrder.indexOf(message));
      expect(order, 'newest in front, each one older than the one before').toEqual([...order].sort((a, b) => b - a));

      await untilStill(page);
      const box = await pillOf(toasts(page).first());
      const bar = (await tabbar.boundingBox())!;
      expect(box.y + box.height, 'the front toast ends above the bottom bar').toBeLessThanOrEqual(bar.y);
      expect(box.x, 'inside the window on the left').toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, 'inside the window on the right').toBeLessThanOrEqual(size.width);
      await capture(page, `toast-stack-three-${size.label}`);

      await toasts(page).last().press('Escape');
      await expect(toastSaying(page, 'Fourth notice')).toBeVisible();
      await expect(toasts(page)).toHaveCount(3);
      await dismissToasts(page);
    });
  }
});

test('the mouse over the stack opens it into a list and stops every clock until it leaves', async ({ page }) => {
  for (const size of THREE_SIZES) {
    await test.step(size.label, async () => {
      await home(page, size);
      await show(page, { message: 'Saved the first', tone: 'success' }, { message: 'Saved the second', tone: 'success' });
      await expect(toasts(page)).toHaveCount(2);

      await toastSaying(page, 'Saved the second').hover();
      await expect(bottomStack(page)).toHaveClass(/is-expanded/);
      await untilStill(page);
      const [front, behind] = [await pillOf(toastSaying(page, 'Saved the second')), await pillOf(toastSaying(page, 'Saved the first'))];
      expect(behind.y + behind.height, 'open, the older toast sits above the newer one').toBeLessThanOrEqual(front.y);
      if (size.label === '1440') await capture(page, 'toast-stack-open-1440');

      await page.waitForTimeout(SUCCESS_MS + 1000);
      await expect(toasts(page), 'paused while the mouse is over the stack').toHaveCount(2);

      await page.mouse.move(0, 0);
      await expect(bottomStack(page)).not.toHaveClass(/is-expanded/);
      await expect(toasts(page)).toHaveCount(0, { timeout: SUCCESS_MS + 2000 });
    });
  }
});

test('an error stays longer than a success and is the one with a close button', async ({ page }) => {
  for (const size of THREE_SIZES) {
    await test.step(size.label, async () => {
      await home(page, size);
      const shownAt = Date.now();
      await show(page, { message: 'Changes saved', tone: 'success' }, { message: 'Could not send it', tone: 'error' });

      const success = toastSaying(page, 'Changes saved');
      const error = toastSaying(page, 'Could not send it');
      await expect(error).toHaveAttribute('data-tone', 'error');
      await expect(error).toHaveAttribute('role', 'alert');
      await expect(error.getByRole('button', { name: CLOSE })).toBeVisible();
      await expect(success.getByRole('button', { name: CLOSE })).toHaveCount(0);

      await expect(success).toHaveCount(0, { timeout: SUCCESS_MS + 1500 });
      expect(Date.now() - shownAt, 'the success left before the error could').toBeLessThan(ERROR_MS);
      await expect(error).toBeVisible();
      await error.getByRole('button', { name: CLOSE }).click();
      await expect(toasts(page)).toHaveCount(0);
    });
  }
});

test('with the assistant docked beside the screen, the stack is centred on the screen it shares the window with', async ({ page }) => {
  for (const size of THREE_SIZES.filter((each) => each.width >= 768)) {
    await test.step(size.label, async () => {
      await home(page, size);
      expect(compactBar(page)).toBe(false);
      const panel = page.locator('[data-testid="assistant-panel"]');
      if ((await panel.getAttribute('data-open')) !== 'true') await shown(page).locator('[data-testid="assistant-button"]').click();
      await expect(panel).toHaveAttribute('data-open', 'true');
      await expect(page.locator('html')).toHaveClass(/assistant-docked/);
      await page.mouse.move(0, 0);

      await show(page, { message: 'Report sent', tone: 'info', duration: 0 });
      await expect(toastSaying(page, 'Report sent')).toBeVisible();
      await untilStill(page);
      const side = (await panel.boundingBox())!;
      const box = await pillOf(toastSaying(page, 'Report sent'));
      expect(box.x + box.width, 'the toast never lies under the panel').toBeLessThanOrEqual(side.x);
      expect(Math.abs(box.x + box.width / 2 - side.x / 2), 'centred on the screen beside the panel').toBeLessThanOrEqual(2);
      await capture(page, `toast-stack-assistant-${size.label}`);

      await shown(page).locator('[data-testid="assistant-button"]').click();
      await expect(panel).not.toHaveAttribute('data-open', 'true');
    });
  }
});
