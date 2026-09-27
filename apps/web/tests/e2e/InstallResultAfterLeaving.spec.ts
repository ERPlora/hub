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
const ANSWER_AFTER_MS = 2500;

interface Notice { text: string; top: number; bottom: number; left: number; right: number }

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

async function installThenLeaveBySideMenu(page: Page, answer: 'error' | 'success'): Promise<{ calls: () => number }> {
  let calls = 0;
  await page.route(/\/api\/marketplace\/catalog/, (r) => r.fulfill({ json: [APP] }));
  await page.route(/\/api\/modules\/flows\/versions/, (r) => r.fulfill({ json: { versions: [] } }));
  await page.route(/\/api\/modules\/flows\/capabilities/, (r) =>
    r.request().method() === 'PUT'
      ? r.fulfill({ json: { ok: true } })
      : r.fulfill({ status: 404, json: { error: 'unknown module' } }),
  );
  await page.route(/\/api\/modules\/request-install/, async (r) => {
    calls += 1;
    await new Promise((res) => setTimeout(res, ANSWER_AFTER_MS));
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

  // Below the split-pane breakpoint the side menu is behind the hamburger.
  const hamburger = page.locator('ion-menu-button:not(.menu-button-hidden)').first();
  if (await hamburger.isVisible()) await hamburger.click();
  await page.locator('ion-item.nav-item').filter({ hasText: 'Ajustes' }).first().click();
  await expect(page).toHaveURL(/\/settings/);
  return { calls: () => calls };
}

const SIZES = [
  { width: 1920, height: 1080 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
];

test.describe('leaving Apps while an app installs (hub#2252)', () => {
  for (const { width, height } of SIZES) {
    test(`${width}px: the error reaches the new screen, with «Reintentar», and «Instalando…» goes`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await installThenLeaveBySideMenu(page, 'error');

      await expect
        .poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(SENTENCE)), { timeout: 8000 })
        .toBe(true);
      await page.waitForTimeout(600); // the replaced notice finishes leaving
      const notices = await visibleNotices(page);
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
    });
  }

  test('«Reintentar» on the new screen asks the runtime again', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const install = await installThenLeaveBySideMenu(page, 'error');
    const retry = page.locator('ion-toast:not(.overlay-hidden)').getByRole('button', { name: 'Reintentar' });
    await expect(retry).toBeVisible({ timeout: 8000 });
    expect(install.calls()).toBe(1);

    await retry.click();
    await expect.poll(install.calls).toBe(2);
    await expect
      .poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(INSTALLING)))
      .toBe(true);
  });

  test('a successful install says so on the new screen, and «Instalando…» goes', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installThenLeaveBySideMenu(page, 'success');

    await expect
      .poll(async () => (await visibleNotices(page)).some((n) => n.text.includes(INSTALLED)), { timeout: 8000 })
      .toBe(true);
    await page.waitForTimeout(600);
    expect((await visibleNotices(page)).filter((n) => n.text.includes(INSTALLING))).toEqual([]);
  });

  test('while it is still running, the new screen keeps saying «Instalando…»', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installThenLeaveBySideMenu(page, 'success');

    await page.waitForTimeout(700);
    const notices = await visibleNotices(page);
    expect(notices.some((n) => n.text.includes(INSTALLING))).toBe(true);
    const installing = notices.find((n) => n.text.includes(INSTALLING))!;
    expect(installing.top).toBeGreaterThanOrEqual(0);
    expect(installing.bottom).toBeLessThanOrEqual(1080);
  });
});
