// Regression test for ERPlora/hub#2244 — on a desktop, a failed install left no readable trace.
//
// Recorded on 2026-09-26 (1920x1080): «Install» → «Install and grant», the dialog closed, the row
// stayed «Available», and the only sign of the failure was a red toast peeking one pixel above the
// bottom edge that never came up. Measured on this bench before the fix, the same click with the
// install failing within 0–400 ms: the red toast rose, dropped half out of the window, rose again ON
// TOP of the Apps tab bar (bottom edge 1070 of 1080, tabs under it) and was gone before 2 s —
// shorter than its own 2.5 s, because the late `didDismiss` of «Installing…» closed it too.
//
// The bench has no Cloud, so the catalogue and the failing request-install are answered here;
// everything else — shell, Ionic, the toast, its animation — is the real thing.
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
  // Declares a permission → the consent dialog, «Install and grant», exactly as recorded.
  capabilities: { manage_flows: {} },
};

const SENTENCE = 'The marketplace did not answer in time';

interface Box { top: number; bottom: number; left: number; right: number }

async function openCatalogueWithFailingInstall(page: Page, failAfterMs: number): Promise<{ calls: () => number }> {
  let calls = 0;
  await page.route(/\/api\/marketplace\/catalog/, (r) => r.fulfill({ json: [APP] }));
  await page.route(/\/api\/modules\/flows\/versions/, (r) => r.fulfill({ json: { versions: [] } }));
  await page.route(/\/api\/modules\/flows\/capabilities/, (r) => r.fulfill({ status: 404, json: { error: 'unknown module' } }));
  await page.route(/\/api\/modules\/request-install/, async (r) => {
    calls += 1;
    await new Promise((res) => setTimeout(res, failAfterMs));
    await r.fulfill({ status: 502, json: { error: SENTENCE } });
  });
  await loggedInSession(page);
  await page.goto('/apps#all');
  await page.getByRole('button', { name: 'Instalar', exact: true }).first().click();
  await page.getByRole('button', { name: 'Instalar y conceder' }).click();
  return { calls: () => calls };
}

/** The wrapper of the presented `ion-toast` (the host is full-screen; the wrapper is what you see). */
async function toastBox(page: Page): Promise<(Box & { text: string; hidden: boolean }) | null> {
  return page.evaluate(() => {
    const host = document.querySelector('ion-toast');
    const wrapper = host?.shadowRoot?.querySelector('.toast-wrapper');
    if (!host || !wrapper) return null;
    const r = wrapper.getBoundingClientRect();
    return {
      top: r.top, bottom: r.bottom, left: r.left, right: r.right,
      text: (wrapper.textContent ?? '').trim(),
      hidden: host.classList.contains('overlay-hidden'),
    };
  });
}

async function tabBarTop(page: Page): Promise<number> {
  const box = await page.locator('ion-segment.ok-tabbar').boundingBox();
  expect(box, 'the Apps tab bar must be on screen').not.toBeNull();
  return box!.y;
}

const SIZES = [
  { width: 1920, height: 1080 },
  { width: 1440, height: 900 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
];

test.describe('a failed install stays readable (hub#2244)', () => {
  for (const { width, height } of SIZES) {
    for (const failAfterMs of [0, 400]) {
      test(`${width}px, failing after ${failAfterMs} ms: the error stays up, inside the window, above the tabs`, async ({ page }) => {
        await page.setViewportSize({ width, height });
        await openCatalogueWithFailingInstall(page, failAfterMs);

        // Past the old 2.5 s and the whole present/dismiss chain: it is still there, and still.
        await page.waitForTimeout(4000);
        const first = await toastBox(page);
        await page.waitForTimeout(300);
        const box = await toastBox(page);
        expect(box, 'the error notice must still be presented').not.toBeNull();
        expect(box!.hidden, 'the error notice must still be presented').toBe(false);
        expect(box!.text).toContain(SENTENCE);
        expect(box!.top, 'settled, not moving').toBeCloseTo(first!.top, 0);

        expect(box!.top).toBeGreaterThanOrEqual(0);
        expect(box!.left).toBeGreaterThanOrEqual(0);
        expect(box!.right).toBeLessThanOrEqual(width);
        expect(box!.bottom, 'inside the window').toBeLessThanOrEqual(height);
        expect(box!.bottom, 'above the Apps tab bar, not over it').toBeLessThanOrEqual(await tabBarTop(page));
      });
    }
  }

  test('«Reintentar» asks the runtime again, and «Cerrar» closes the notice', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const install = await openCatalogueWithFailingInstall(page, 0);
    const retry = page.locator('ion-toast').getByRole('button', { name: 'Reintentar' });
    await expect(retry).toBeVisible();
    expect(install.calls()).toBe(1);

    await retry.click();
    await expect.poll(install.calls).toBe(2);

    const close = page.locator('ion-toast').getByRole('button', { name: 'Cerrar' });
    await expect(close).toBeVisible();
    await close.click();
    await expect(page.locator('ion-toast')).toHaveClass(/overlay-hidden/);
  });
});
