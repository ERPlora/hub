// Regression test for ERPlora/hub#2252 — leaving Apps through the side menu while an app installs.
//
// Measured before the fix on this bench (1920x1080, request-install answering after 2.5 s, «Ajustes»
// clicked at 0.7 s): five seconds later the only notice on screen was «Instalando Automations…»,
// floating over Settings for good; the result — error or success — never appeared. The side menu
// navigates with `router-direction="root"`, Ionic unmounts AppsPage, and its inline `ion-toast`
// (already presented, sticky) was left behind in `ion-app` while the pending install wrote its
// outcome into a component that no longer existed.
//
// The promise: the outcome shows up where the person is, and «Instalando…» goes away when it ends.
import type { Page } from '@playwright/test';
import { test, expect } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

const APP = {
  id: 'flows',
  name: 'Automations',
  description: 'Flows',
  is_free: true,
  installed: false,
  can_install: true,
  version: '1.0.0',
  category: 'Tools',
  capabilities: { manage_flows: {} },
};

const SENTENCE = 'The marketplace did not answer in time';
const INSTALLING = 'Instalando Automations';
const INSTALLED = 'Automations instalado correctamente.';
/** Longer than the 2.5 s the runtime's answer used to be timed at (hub#2296). */
const SLOW_SCREEN_MS = 2500;

interface Notice {
  text: string;
  top: number;
  bottom: number;
  left: number;
  right: number;
}

/** Every notice actually on screen: presented (not `overlay-hidden`) and with a box. */
async function visibleNotices(page: Page): Promise<Notice[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('ion-toast')]
      .filter((host) => !host.classList.contains('overlay-hidden'))
      .map((host) => {
        const wrapper = host.shadowRoot?.querySelector('.toast-wrapper');
        const r = wrapper?.getBoundingClientRect();
        return {
          text: (wrapper?.textContent ?? '').trim(),
          top: r?.top ?? -1,
          bottom: r?.bottom ?? -1,
          left: r?.left ?? -1,
          right: r?.right ?? -1,
        };
      })
      .filter((n) => n.bottom > n.top),
  );
}

/**
 * Every notice on screen once none of them is moving: their enter and leave animations have
 * ended. Not a fixed wait — on a loaded machine a notice was still sliding in after 600 ms and
 * was measured half-way, outside the window (hub#2296).
 */
async function settledNotices(page: Page): Promise<Notice[]> {
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          [...document.querySelectorAll('ion-toast')].some((host) =>
            [...host.getAnimations(), ...(host.shadowRoot?.getAnimations() ?? [])].some(
              (a) => a.playState === 'running',
            ),
          ),
        ),
      { message: 'the notices never stopped moving', timeout: 15_000 },
    )
    .toBe(false);
  return visibleNotices(page);
}

async function installThenLeaveBySideMenu(
  page: Page,
  answer: 'error' | 'success',
  { screenDelayMs = 0 }: { screenDelayMs?: number } = {},
): Promise<{ calls: () => number; answer: () => void }> {
  // The runtime answers when the TEST says so, never on a timer: a timer races the navigation,
  // and on a loaded runner the answer landed before the new screen was even measured (hub#2296).
  let calls = 0;
  const unanswered: Array<() => void> = [];
  if (screenDelayMs > 0) {
    // Only the screen's own module: its style and template parts come after it, in series.
    await page.route(
      (url) => url.pathname === '/src/views/SettingsPage.vue' && url.search === '',
      async (r) => {
        await new Promise((res) => setTimeout(res, screenDelayMs));
        await r.continue();
      },
    );
  }
  await page.route(/\/api\/marketplace\/catalog/, (r) => r.fulfill({ json: [APP] }));
  await page.route(/\/api\/modules\/flows\/versions/, (r) => r.fulfill({ json: { versions: [] } }));
  await page.route(/\/api\/modules\/flows\/capabilities/, (r) =>
    r.request().method() === 'PUT'
      ? r.fulfill({ json: { ok: true } })
      : r.fulfill({ status: 404, json: { error: 'unknown module' } }),
  );
  await page.route(/\/api\/modules\/request-install/, async (r) => {
    calls += 1;
    await new Promise<void>((release) => unanswered.push(release));
    if (answer === 'error') {
      await r.fulfill({ status: 424, json: { ok: false, error: SENTENCE } });
    } else {
      await r.fulfill({
        json: { ok: true, module_id: 'flows', version: '1.0.0', status: 'installed', also_installed: [] },
      });
    }
  });
  await loggedInSession(page);
  await page.goto('/apps#all');
  await page.getByRole('button', { name: 'Instalar', exact: true }).first().click();
  await page.getByRole('button', { name: 'Instalar y conceder' }).click();
  await expect.poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(INSTALLING))).toBe(true);
  await expect.poll(() => calls).toBe(1);

  // Below the split-pane breakpoint the side menu is behind the hamburger.
  const hamburger = page.locator('ion-menu-button:not(.menu-button-hidden)').first();
  if (await hamburger.isVisible()) await hamburger.click();
  await page.locator('ion-item.nav-item').filter({ hasText: 'Ajustes' }).first().click();
  await expect(page).toHaveURL(/\/settings/, { timeout: 5000 + screenDelayMs });
  return { calls: () => calls, answer: () => unanswered.splice(0).forEach((release) => release()) };
}

async function expectErrorOnScreen(page: Page, width: number, height: number): Promise<void> {
  await expect
    .poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(SENTENCE)), { timeout: 8000 })
    .toBe(true);
  const notices = await settledNotices(page);
  const error = notices.find((n) => n.text.includes(SENTENCE))!;
  expect(error.text, 'the way to try again travels with it').toContain('Reintentar');
  expect(error.top).toBeGreaterThanOrEqual(0);
  expect(error.left).toBeGreaterThanOrEqual(0);
  expect(error.right).toBeLessThanOrEqual(width);
  expect(error.bottom, 'inside the window').toBeLessThanOrEqual(height);
  expect(
    notices.filter((n) => n.text.includes(INSTALLING)),
    '«Instalando…» must not outlive the install',
  ).toEqual([]);
}

const SIZES = [
  { width: 1920, height: 1080 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
];

test.describe('leaving Apps while an app installs (hub#2252)', () => {
  for (const { width, height } of SIZES) {
    test(`${width}px: the error reaches the new screen, with «Reintentar», and «Instalando…» goes`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      const install = await installThenLeaveBySideMenu(page, 'error');
      install.answer();
      await expectErrorOnScreen(page, width, height);
    });
  }

  test('a notice that is still sliding in is measured where it stops, not half-way', async ({ page }) => {
    // hub#2296: on a loaded machine the error notice was still sliding up when a fixed 600 ms
    // wait ran out, and it was measured with its bottom at 916 of 844. Here every notice
    // animation that starts after the answer is held on its first frame for three seconds, so a
    // measure that does not wait for the animations to end always catches the notice below the
    // window, where it starts.
    await page.setViewportSize({ width: 390, height: 844 });
    const install = await installThenLeaveBySideMenu(page, 'error');
    await page.evaluate((heldMs) => {
      const animate = Element.prototype.animate;
      Element.prototype.animate = function (this: Element, ...args: Parameters<Element['animate']>) {
        const animation = animate.apply(this, args);
        if (this.classList.contains('toast-wrapper')) animation.effect?.updateTiming({ delay: heldMs });
        return animation;
      };
    }, 3000);
    install.answer();
    await expectErrorOnScreen(page, 390, 844);
  });

  test('a screen that is slow to open does not let the answer overtake the navigation', async ({ page }) => {
    // hub#2296, run 36402437763 attempt 3: on the loaded runner the side menu took 0.8 s to take
    // the click (the consent dialog was still leaving) and Settings 1 s more to open, so the
    // answer — then timed 2.5 s after the install began — landed inside the 700 ms this test
    // waits on the new screen. «Instalando…» was measured while leaving, bottom at 1123 of 1080,
    // on an install that had already ended. The screen is made slower than that timer on purpose.
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installThenLeaveBySideMenu(page, 'success', { screenDelayMs: SLOW_SCREEN_MS });

    await page.waitForTimeout(700);
    const notices = await visibleNotices(page);
    expect(
      notices.some((n) => n.text.includes(INSTALLING)),
      'the install is still running',
    ).toBe(true);
  });

  test('«Reintentar» on the new screen asks the runtime again', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const install = await installThenLeaveBySideMenu(page, 'error');
    install.answer();
    const retry = page.locator('ion-toast:not(.overlay-hidden)').getByRole('button', { name: 'Reintentar' });
    await expect(retry).toBeVisible({ timeout: 8000 });
    expect(install.calls()).toBe(1);

    await retry.click();
    await expect.poll(install.calls).toBe(2);
    await expect.poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(INSTALLING))).toBe(true);
  });

  test('a successful install says so on the new screen, and «Instalando…» goes', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const install = await installThenLeaveBySideMenu(page, 'success');
    install.answer();

    await expect
      .poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(INSTALLED)), { timeout: 8000 })
      .toBe(true);
    expect((await settledNotices(page)).filter((n) => n.text.includes(INSTALLING))).toEqual([]);
  });

  test('while it is still running, the new screen keeps saying «Instalando…»', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installThenLeaveBySideMenu(page, 'success');

    await page.waitForTimeout(700); // time passes on the new screen; the install has not answered
    const notices = await settledNotices(page);
    expect(notices.some((n) => n.text.includes(INSTALLING))).toBe(true);
    const installing = notices.find((n) => n.text.includes(INSTALLING))!;
    expect(installing.top).toBeGreaterThanOrEqual(0);
    expect(installing.bottom).toBeLessThanOrEqual(1080);
  });
});
